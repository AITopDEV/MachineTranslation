import torch
import torch.nn as nn
from torch.autograd import Variable
from onmt.modules.Util import BottleLinear, BottleLayerNorm, BottleSoftmax
import math


class MultiHeadedAttention(nn.Module):
    ''' Multi-Head Attention module '''

    def __init__(self, n_head, d_model, p=0.1):
        self.d_k = d_model // n_head
        self.d_model = d_model

        super(MultiHeadedAttention, self).__init__()
        heads = self.heads = n_head

        self.linear_keys = BottleLinear(d_model, heads * self.d_k, bias=False)
        self.linear_values = BottleLinear(d_model, heads * self.d_k,
                                          bias=False)
        self.linear_query = BottleLinear(d_model, heads * self.d_k, bias=False)
        self.sm = BottleSoftmax()
        self.activation = nn.ReLU()
        self.layer_norm = BottleLayerNorm(d_model)
        self.dropout = nn.Dropout(p)
        self.res_dropout = nn.Dropout(p)

    def forward(self, key, value, query, mask=None):
        # Check Sizes
        batch, t_len, d = key.size()
        batch2, t_len2, d2 = value.size()
        batch3, q_len, d3 = query.size()
        assert batch == batch2
        assert batch == batch3
        assert t_len == t_len2
        assert d == self.d_model

        def shape_projection(x):
            b, l, d = x.size()
            return x.view(b, l, self.heads, self.d_k).transpose(1, 2) \
                    .contiguous().view(b * self.heads, l, self.d_k)

        def unshape_projection(x, q):
            b, l, d = q.size()
            return x.view(b, self.heads, l, self.d_k) \
                    .transpose(1, 2).contiguous() \
                    .view(b, l, self.heads * self.d_k)

        residual = query
        key_up = shape_projection(self.linear_keys(key))
        value_up = shape_projection(self.linear_values(value))
        query_up = shape_projection(self.linear_query(query))

        scaled = torch.bmm(query_up, key_up.transpose(1, 2))
        scaled = scaled / math.sqrt(self.d_k)

        if mask is not None:
            bh, l, d_k = scaled.size()
            b = bh // self.heads
            scaled = scaled.view(b, self.heads, l, d_k)
            mask = mask.unsqueeze(1).expand_as(scaled)
            scaled = scaled.masked_fill(Variable(mask), -float('inf')) \
                           .view(bh, l, d_k)
        attn = self.dropout(self.sm(scaled))

        # values : (batch * 8) x qlen x dim
        out = unshape_projection(torch.bmm(attn, value_up), residual)

        # Residual and layer norm
        res = self.res_dropout(out) + residual
        return self.layer_norm(res), attn
