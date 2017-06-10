# -*- coding: utf-8 -*-

import onmt
import onmt.Markdown
import argparse
import torch
import codecs


def loadImageLibs():
    "Conditional import of torch image libs."
    global Image, transforms
    from PIL import Image
    from torchvision import transforms


parser = argparse.ArgumentParser(description='preprocess.py')
onmt.Markdown.add_md_help_argument(parser)

# **Preprocess Options**

parser.add_argument('-config',    help="Read options from this file")

parser.add_argument('-src_type', default="text",
                    help="Type of the source input. Options are [text|img].")
parser.add_argument('-src_img_dir', default=".",
                    help="Location of source images")


parser.add_argument('-train_src', required=True,
                    help="Path to the training source data")
parser.add_argument('-train_tgt', required=True,
                    help="Path to the training target data")
parser.add_argument('-valid_src', required=True,
                    help="Path to the validation source data")
parser.add_argument('-valid_tgt', required=True,
                    help="Path to the validation target data")

parser.add_argument('-save_data', required=True,
                    help="Output file for the prepared data")

parser.add_argument('-src_vocab_size', type=int, default=50000,
                    help="Size of the source vocabulary")
parser.add_argument('-tgt_vocab_size', type=int, default=50000,
                    help="Size of the target vocabulary")
parser.add_argument('-src_vocab',
                    help="Path to an existing source vocabulary")
parser.add_argument('-tgt_vocab',
                    help="Path to an existing target vocabulary")
parser.add_argument('-features_vocabs_prefix', type=str, default='',
                    help="Path prefix to existing features vocabularies")
parser.add_argument('-src_seq_length', type=int, default=50,
                    help="Maximum source sequence length")
parser.add_argument('-src_seq_length_trunc', type=int, default=0,
                    help="Truncate source sequence length.")
parser.add_argument('-tgt_seq_length', type=int, default=50,
                    help="Maximum target sequence length to keep.")
parser.add_argument('-tgt_seq_length_trunc', type=int, default=0,
                    help="Truncate target sequence length.")

parser.add_argument('-shuffle',    type=int, default=1,
                    help="Shuffle data")
parser.add_argument('-seed',       type=int, default=3435,
                    help="Random seed")

parser.add_argument('-lower', action='store_true', help='lowercase data')

parser.add_argument('-report_every', type=int, default=100000,
                    help="Report status every this many sentences")

opt = parser.parse_args()

torch.manual_seed(opt.seed)


def extractFeatures(tokens):
    "Given a list of token separate out words and features (if any)."
    words = []
    features = []
    numFeatures = None

    for t in range(len(tokens)):
        field = tokens[t].split(u"￨")
        word = field[0]
        if len(word) > 0:
            words.append(word)

            if numFeatures is None:
                numFeatures = len(field) - 1
            else:
                assert (len(field) - 1 == numFeatures), \
                    "all words must have the same number of features"

            if len(field) > 1:
                for i in range(1, len(field)):
                    if len(features) <= i-1:
                        features.append([])
                    features[i - 1].append(field[i])
                    assert (len(features[i - 1]) == len(words))
    return words, features, numFeatures if numFeatures else 0


def makeVocabulary(filename, size):
    "Construct the word and feature vocabs."
    vocab = onmt.Dict([onmt.Constants.PAD_WORD, onmt.Constants.UNK_WORD,
                       onmt.Constants.BOS_WORD, onmt.Constants.EOS_WORD,
                       onmt.Constants.COPY
],
                      lower=opt.lower)
    featuresVocabs = []
    with codecs.open(filename, "r", "utf-8") as f:
        for sent in f.readlines():
            words, features, numFeatures = extractFeatures(sent.split())

            if len(featuresVocabs) == 0 and numFeatures > 0:
                for j in range(numFeatures):
                    featuresVocabs.append(onmt.Dict([onmt.Constants.PAD_WORD,
                                                   onmt.Constants.UNK_WORD,
                                                   onmt.Constants.BOS_WORD,
                                                     onmt.Constants.EOS_WORD,
                                                     onmt.Constants.COPY]))
            else:
                assert len(featuresVocabs) == numFeatures, \
                    "all sentences must have the same number of features"

            for i in range(len(words)):
                vocab.add(words[i])
                for j in range(numFeatures):
                    featuresVocabs[j].add(features[j][i])

    originalSize = vocab.size()
    vocab = vocab.prune(size)
    print('Created dictionary of size %d (pruned from %d)' %
          (vocab.size(), originalSize))

    return vocab, featuresVocabs


def initVocabulary(name, dataFile, vocabFile, vocabSize):
    """If `vocabFile` exists, read it in,
    Else, generate from data."""
    vocab = None
    if vocabFile is not None:
        # If given, load existing word dictionary.
        print('Reading ' + name + ' vocabulary from \'' + vocabFile + '\'...')
        vocab = onmt.Dict()
        vocab.loadFile(vocabFile)
        print('Loaded ' + str(vocab.size()) + ' ' + name + ' words')

    if vocab is None:
        # If a dictionary is still missing, generate it.
        print('Building ' + name + ' vocabulary...')
        genWordVocab, genFeaturesVocabs = makeVocabulary(dataFile, vocabSize)
        vocab = genWordVocab
        featuresVocabs = genFeaturesVocabs

    print()
    return vocab, featuresVocabs


def saveVocabulary(name, vocab, file):
    print('Saving ' + name + ' vocabulary to \'' + file + '\'...')
    vocab.writeFile(file)


def saveFeaturesVocabularies(name, vocabs, prefix):
    for j in range(len(vocabs)):
        file = prefix + '.' + name + '_feature_' + str(j) + '.dict'
        print('Saving ' + name + ' feature ' + str(j) +
              ' vocabulary to \'' + file + '\'...')
        vocabs[j].writeFile(file)


def makeData(srcFile, tgtFile, srcDicts, tgtDicts,
             srcFeatureDicts, tgtFeatureDicts):
    src, tgt = [], []
    srcFeats = [[] for i in range(len(srcFeatureDicts))]
    tgtFeats = [[] for i in range(len(tgtFeatureDicts))]
    sizes = []
    count, ignored = 0, 0

    print('Processing %s & %s ...' % (srcFile, tgtFile))
    srcF = codecs.open(srcFile, "r", "utf-8")
    tgtF = codecs.open(tgtFile, "r", "utf-8")

    while True:
        sline = srcF.readline()
        tline = tgtF.readline()

        # normal end of file
        if sline == "" and tline == "":
            break

        # source or target does not have same number of lines
        if sline == "" or tline == "":
            print('WARNING: src and tgt do not have the same # of sentences')
            break

        sline = sline.strip()
        tline = tline.strip()

        # source and/or target are empty
        if sline == "" or tline == "":
            print('WARNING: ignoring an empty line ('+str(count+1)+')')
            continue

        srcWords, srcFeatures, _ = extractFeatures(sline.split())
        tgtWords, tgtFeatures, _ = extractFeatures(tline.split())

        if len(srcWords) <= opt.src_seq_length \
           and len(tgtWords) <= opt.tgt_seq_length:

            # Check truncation condition.
            if opt.src_seq_length_trunc != 0:
                srcWords = srcWords[:opt.src_seq_length_trunc]
                srcFeatures = srcFeatures[:opt.src_seq_length_trunc]
            if opt.tgt_seq_length_trunc != 0:
                tgtWords = tgtWords[:opt.tgt_seq_length_trunc]
                tgtFeatures = tgtFeatures[:opt.tgt_seq_length_trunc]

            if opt.src_type == "text":
                src += [srcDicts.convertToIdx(srcWords,
                                              onmt.Constants.UNK_WORD)]
                if srcFeatureDicts:
                    for j in range(len(srcFeatureDicts)):
                        srcFeats[j] += [srcFeatureDicts[j].
                                        convertToIdx(srcFeatures[j],
                                                     onmt.Constants.UNK_WORD)]
            elif opt.src_type == "img":
                loadImageLibs()
                src += [transforms.ToTensor()(
                    Image.open(opt.src_img_dir + "/" + srcWords[0]))]

            sizes += [len(srcWords)]
            tgt += [tgtDicts.convertToIdx(tgtWords,
                                          onmt.Constants.UNK_WORD,
                                          onmt.Constants.BOS_WORD,
                                          onmt.Constants.EOS_WORD)]
            if tgtFeatureDicts:
                for j in range(len(tgtFeatureDicts)):
                    tgtFeats[j] += [tgtFeatureDicts[j].
                                    convertToIdx(tgtFeatures[j],
                                                 onmt.Constants.UNK_WORD)]
        else:
            ignored += 1

        count += 1

        if count % opt.report_every == 0:
            print('... %d sentences prepared' % count)

    srcF.close()
    tgtF.close()

    if opt.shuffle == 1:
        print('... shuffling sentences')
        perm = torch.randperm(len(src))
        src = [src[idx] for idx in perm]
        tgt = [tgt[idx] for idx in perm]
        for j in range(len(srcFeatureDicts)):
            srcFeats[j] = [srcFeats[j][idx] for idx in perm]
        for j in range(len(tgtFeatureDicts)):
            tgtFeats[j] = [tgtFeats[j][idx] for idx in perm]
        sizes = [sizes[idx] for idx in perm]

    print('... sorting sentences by size')
    _, perm = torch.sort(torch.Tensor(sizes))
    src = [src[idx] for idx in perm]
    tgt = [tgt[idx] for idx in perm]
    for j in range(len(srcFeatureDicts)):
        srcFeats[j] = [srcFeats[j][idx] for idx in perm]
    for j in range(len(tgtFeatureDicts)):
        tgtFeats[j] = [tgtFeats[j][idx] for idx in perm]

    print(('Prepared %d sentences ' +
          '(%d ignored due to length == 0 or src len > %d or tgt len > %d)') %
          (len(src), ignored, opt.src_seq_length, opt.tgt_seq_length))

    return src, tgt, srcFeats, tgtFeats


def main():

    dicts = {}
    dicts['src'] = onmt.Dict()
    if opt.src_type == "text":
        dicts['src'], dicts['src_features'] = \
                initVocabulary('source', opt.train_src, opt.src_vocab,
                               opt.src_vocab_size)

    dicts['tgt'], dicts['tgt_features'] = \
        initVocabulary('target',
                       opt.train_tgt,
                       opt.tgt_vocab,
                       opt.tgt_vocab_size)

    print('Preparing training ...')
    train = {}
    train['src'], train['tgt'], train['src_features'], train['tgt_features'] \
        = makeData(opt.train_src, opt.train_tgt,
                   dicts['src'], dicts['tgt'],
                   dicts['src_features'], dicts['tgt_features'])
    print('Preparing validation ...')
    valid = {}
    valid['src'], valid['tgt'], valid['src_features'], valid['tgt_features'] \
        = makeData(opt.valid_src, opt.valid_tgt,
                   dicts['src'], dicts['tgt'],
                   dicts['src_features'], dicts['tgt_features'])

    if opt.src_vocab is None:
        saveVocabulary('source', dicts['src'], opt.save_data + '.src.dict')
    if opt.tgt_vocab is None:
        saveVocabulary('target', dicts['tgt'], opt.save_data + '.tgt.dict')
    if opt.features_vocabs_prefix:
        saveFeaturesVocabularies('source', dicts['src_features'],
                                 opt.save_data)
        saveFeaturesVocabularies('target', dicts['tgt_features'],
                                 opt.save_data)

    print('Saving data to \'' + opt.save_data + '.train.pt\'...')
    save_data = {'dicts': dicts,
                 'type':  opt.src_type,
                 'train': train,
                 'valid': valid}
    torch.save(save_data, opt.save_data + '.train.pt')


if __name__ == "__main__":
    main()
