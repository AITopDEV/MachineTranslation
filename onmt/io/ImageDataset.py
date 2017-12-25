# -*- coding: utf-8 -*-

import codecs
import os

from onmt.io.IO import ONMTDatasetBase


class ImageDataset(ONMTDatasetBase):
    """ Dataset for data_type=='img'

        Build `Example` objects, `Field` objects, and filter_pred function
        from image corpus.

        Args:
            fields (dict): a dictionary of `torchtext.data.Field`.
            src_examples_iter (dict iter): preprocessed source example
                dictionary iterator.
            tgt_examples_iter (dict iter): preprocessed target example
                dictionary iterator.
            num_src_feats (int): number of source side features.
            num_tgt_feats (int): number of target side features.
            tgt_seq_length (int): maximum target sequence length.
            use_filter_pred (bool): use a custom filter predicate to filter
                out examples?
    """
    def __init__(self, fields, src_examples_iter, tgt_examples_iter,
                 num_src_feats=0, num_tgt_feats=0,
                 tgt_seq_length=0, use_filter_pred=True):
        self.data_type = 'img'

        self.n_src_feats = num_src_feats
        self.n_tgt_feats = num_tgt_feats

        if tgt_examples_iter is not None:
            examples_iter = (self._join_dicts(src, tgt) for src, tgt in
                             zip(src_examples_iter, tgt_examples_iter))
        else:
            examples_iter = src_examples_iter

        # Peek at the first to see which fields are used.
        ex, examples_iter = self._peek(examples_iter)
        keys = ex.keys()

        out_fields = [(k, fields[k]) if k in fields else (k, None)
                      for k in keys]
        example_values = ([ex[k] for k in keys] for ex in examples_iter)
        out_examples = (self._construct_example_fromlist(
                            ex_values, out_fields)
                        for ex_values in example_values)

        def filter_pred(example):
            if tgt_examples_iter is not None:
                return 0 < len(example.tgt) <= tgt_seq_length
            else:
                return True

        filter_pred = filter_pred if use_filter_pred else lambda x: True

        super(ImageDataset, self).__init__(
            out_examples, out_fields, filter_pred
        )

    def sort_key(self, ex):
        "Sort using the size of the image."
        return (-ex.src.size(2), -ex.src.size(1))

    @staticmethod
    def read_img_file(path, src_dir, side, truncate=None):
        """
        Args:
            path: location of a src file containing image paths
            src_dir: location of source images
            side: 'src' or 'tgt'
            truncate: maximum img size ((0,0) or None for unlimited)

        Yields:
            a dictionary containing image data, path and index for each line.
        """
        assert (src_dir is not None) and os.path.exists(src_dir),\
            'src_dir must be a valid directory if data_type is img'

        global Image, transforms
        from PIL import Image
        from torchvision import transforms

        with codecs.open(path, "r", "utf-8") as corpus_file:
            index = 0
            for line in corpus_file:
                img_path = os.path.join(src_dir, line.strip())
                if not os.path.exists(img_path):
                    img_path = line

                assert os.path.exists(img_path), \
                    'img path %s not found' % (line.strip())

                img = transforms.ToTensor()(Image.open(img_path))
                if truncate and truncate != (0, 0):
                    if not (img.size(1) <= truncate[0]
                            and img.size(2) <= truncate[1]):
                        continue

                example_dict = {side: img,
                                side+'_path': line.strip(),
                                'indices': index}
                index += 1

                yield example_dict
