import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from pkg.modules import MaskedConv1d, HighwayConv1d, CharEmbed
from pkg.modules import SequentialMaker
from pkg.hyper import Hyper


class TextEncoder(nn.Module):
    def __init__(self):
        super(TextEncoder, self).__init__()
        seq = SequentialMaker()
        seq.add_module("char-embed",  CharEmbed(len(Hyper.vocab), Hyper.dim_e, Hyper.vocab.find('P')))
        seq.add_module("conv_0",      MaskedConv1d(Hyper.dim_e, Hyper.dim_d * 2, 1, padding="same"))
        seq.add_module("relu_0",      nn.ReLU())
        seq.add_module("drop_0",      nn.Dropout(Hyper.dropout))
        seq.add_module("conv_1",      MaskedConv1d(Hyper.dim_d * 2, Hyper.dim_d * 2, 1, padding="same"))
        seq.add_module("drop_1",      nn.Dropout(Hyper.dropout))
        i = 2
        for _ in range(2):
            for j in range(4):
                seq.add_module("highway-conv_{}".format(i),
                               HighwayConv1d(Hyper.dim_d * 2,
                                             kernel_size=3,
                                             dilation=3 ** j,
                                             padding="same"))
                seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
                i += 1
        for j in [1, 0]:
            for k in range(2):
                seq.add_module("highway-conv_{}".format(i),
                               HighwayConv1d(Hyper.dim_d * 2,
                                             kernel_size=3 ** j,
                                             dilation=1,
                                             padding="same"))
                if not (j == 0 and k == 1):
                    seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
                i += 1
        self.seq_ = seq()

    def forward(self, inputs):
        outputs = self.seq_(inputs)
        k, v = torch.chunk(outputs, 2, 1)
        return k, v

    def print_shape(self, input_shape):
        print("text-encode {")
        SequentialMaker.print_shape(
            self.seq_,
            torch.LongTensor(np.zeros(input_shape)),
            intent_size=2)
        print("}")


class AudioEncoder(nn.Module):
    def __init__(self):
        super(AudioEncoder, self).__init__()
        seq = SequentialMaker()
        seq.add_module("conv_0", MaskedConv1d(Hyper.dim_f, Hyper.dim_d, 1, padding="causal"))
        seq.add_module("relu_0", nn.ReLU())
        seq.add_module("drop_0", nn.Dropout(Hyper.dropout))
        seq.add_module("conv_1", MaskedConv1d(Hyper.dim_d, Hyper.dim_d, 1, padding="causal"))
        seq.add_module("relu_1", nn.ReLU())
        seq.add_module("drop_1", nn.Dropout(Hyper.dropout))
        seq.add_module("relu_2", MaskedConv1d(Hyper.dim_d, Hyper.dim_d, 1, padding="causal"))
        seq.add_module("drop_2", nn.Dropout(Hyper.dropout))
        i = 3
        for _ in range(2):
            for j in range(4):
                seq.add_module("highway-conv_{}".format(i),
                               HighwayConv1d(Hyper.dim_d,
                                             kernel_size=3,
                                             dilation=3 ** j,
                                             padding="causal"))
                seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
                i += 1
        for k in range(2):
            seq.add_module("highway-conv_{}".format(i),
                           HighwayConv1d(Hyper.dim_d,
                                         kernel_size=3,
                                         dilation=3,
                                         padding="causal"))
            if k == 0:
                seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
            i += 1
        self.seq_ = seq()

    def forward(self, inputs):
        return self.seq_(inputs)

    def print_shape(self, input_shape):
        print("audio-encoder {")
        SequentialMaker.print_shape(
            self.seq_,
            torch.FloatTensor(np.zeros(input_shape)),
            intent_size=2)
        print("}")


class AudioDecoder(nn.Module):
    def __init__(self):
        super(AudioDecoder, self).__init__()
        seq = SequentialMaker()
        seq.add_module("conv_0", MaskedConv1d(Hyper.dim_d * 2, Hyper.dim_d, 1, padding="causal"))
        seq.add_module("drop_0", nn.Dropout(Hyper.dropout))
        i = 1
        for _ in range(1):
            for j in range(4):
                seq.add_module("highway-conv_{}".format(i),
                               HighwayConv1d(Hyper.dim_d,
                                             kernel_size=3,
                                             dilation=3 ** j,
                                             padding="causal"))
                seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
                i += 1
        for _ in range(2):
            seq.add_module("highway-conv_{}".format(i),
                           HighwayConv1d(Hyper.dim_d,
                                         kernel_size=3,
                                         dilation=1,
                                         padding="causal"))
            seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
            i += 1
        for _ in range(3):
            seq.add_module("conv_{}".format(i),
                           MaskedConv1d(Hyper.dim_d, Hyper.dim_d,
                                        kernel_size=1,
                                        dilation=1,
                                        padding="causal"))
            seq.add_module("relu_{}".format(i), nn.ReLU())
            seq.add_module("drop_{}".format(i), nn.Dropout(Hyper.dropout))
            i += 1
        seq.add_module("conv_{}".format(i), MaskedConv1d(Hyper.dim_d, Hyper.dim_f, 1, 1, padding="causal"))
        self.seq_ = seq()

    def forward(self, inputs):
        return self.seq_(inputs)

    def print_shape(self, input_shape):
        print("audio-decoder {")
        SequentialMaker.print_shape(
            self.seq_,
            torch.FloatTensor(np.zeros(input_shape)),
            intent_size=2)
        print("}")


class Text2Mel(nn.Module):
    def __init__(self):
        super(Text2Mel, self).__init__()
        self.texts_enc_ = TextEncoder()
        self.audio_enc_ = AudioEncoder()
        self.audio_dec_ = AudioDecoder()
        self.sigmoid_ = nn.Sigmoid()

    def forward(self, texts, shift_mels):
        k, v = self.texts_enc_(texts)
        q = self.audio_enc_(shift_mels)
        a = F.softmax(torch.bmm(k.transpose(1, 2), q) / np.sqrt(Hyper.dim_d), 1)
        r = torch.cat((torch.bmm(v, a), q), 1)
        mel_logits = self.audio_dec_(r)

        self.query = q
        self.attention = a
        self.mels = self.sigmoid_(mel_logits)
        return mel_logits, self.mels
