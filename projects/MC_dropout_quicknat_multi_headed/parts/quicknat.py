"""Quicknat architecture"""
import numpy as np
import torch
import torch.nn as nn
from nn_common_modules import modules as sm
from squeeze_and_excitation import squeeze_and_excitation as se


class QuickNat(nn.Module):
    """
    A PyTorch implementation of QuickNAT

    """

    def __init__(self, params):
        """

        :param params: {'num_channels':1,
                        'num_filters':64,
                        'kernel_h':5,
                        'kernel_w':5,
                        'stride_conv':1,
                        'pool':2,
                        'stride_pool':2,
                        'num_classes':28
                        'se_block': False,
                        'drop_out':0.2}
        """
        super(QuickNat, self).__init__()
        self.scalara_in = sm.ScalarInput(params)
        self.encode1 = sm.EncoderBlock(params, se_block_type=se.SELayer.CSSE)
        params['num_channels'] = 64
        self.encode2 = sm.EncoderBlock(params, se_block_type=se.SELayer.CSSE)
        self.encode3 = sm.EncoderBlock(params, se_block_type=se.SELayer.CSSE)
        self.encode4 = sm.EncoderBlock(params, se_block_type=se.SELayer.CSSE)
        self.bottleneck = sm.DenseBlock(params, se_block_type=se.SELayer.CSSE)
        params['num_channels'] = 128
        self.decode1 = sm.DecoderBlock(params, se_block_type=se.SELayer.CSSE)
        self.decode2 = sm.DecoderBlock(params, se_block_type=se.SELayer.CSSE)
        self.decode3 = sm.DecoderBlock(params, se_block_type=se.SELayer.CSSE)
        self.decode4 = sm.DecoderBlock(params, se_block_type=se.SELayer.CSSE)
        params['num_channels'] = 64
        self.classifier = sm.ClassifierBlockMultiHeaded(params)

        self.is_training = True

    def forward(self, input):
        """

        :param input: X
        :return: probabiliy map
        """
        if not self.is_training:
            self.enable_test_dropout()

        e1, out1, ind1 = self.encode1(input)
        e2, out2, ind2 = self.encode2(e1)
        e3, out3, ind3 = self.encode3(e2)
        e4, out4, ind4 = self.encode4(e3)

        bn = self.bottleneck(e4)

        d4 = self.decode4(bn, out4, ind4)
        d3 = self.decode1(d4, out3, ind3)
        d2 = self.decode2(d3, out2, ind2)
        d1 = self.decode3(d2, out1, ind1)
        prob, scalar_prob = self.classifier(d1)

        return None, None, (prob, scalar_prob)

    def set_is_training(self, is_training):
        self.is_training = is_training

    def enable_test_dropout(self):
        """
        Enables test time drop out for uncertainity
        :return:
        """
        attr_dict = self.__dict__['_modules']
        for i in range(1, 5):
            encode_block, decode_block = attr_dict['encode' + str(i)], attr_dict['decode' + str(i)]
            encode_block.drop_out = encode_block.drop_out.apply(nn.Module.train)
            decode_block.drop_out = decode_block.drop_out.apply(nn.Module.train)

    @property
    def is_cuda(self):
        """
        Check if saved_models parameters are allocated on the GPU.
        """
        return next(self.parameters()).is_cuda

    def save(self, path):
        """
        Save saved_models with its parameters to the given path. Conventionally the
        path should end with '*.saved_models'.

        Inputs:
        - path: path string
        """
        print('Saving saved_models... %s' % path)
        torch.save(self, path)

    def predict(self, X, device=0, enable_dropout=True, forward_out=False):
        """
        Predicts the outout after the saved_models is trained.
        Inputs:
        - X: Volume to be predicted
        """
        self.eval()

        if type(X) is np.ndarray:
            X = torch.tensor(X, requires_grad=False).type(torch.FloatTensor).cuda(device, non_blocking=True)
        elif type(X) is torch.Tensor and not X.is_cuda:
            X = X.type(torch.FloatTensor).cuda(device, non_blocking=True)

        if enable_dropout:
            self.enable_test_dropout()

        with torch.no_grad():
            o = self.forward(X)
            out, scalar_out = o[2]
            # out = out[0]
            # scalar_out = out[1]

        if forward_out:
            return out
        else:
            max_val, idx = torch.max(out, 1)
            idx = idx.data.cpu().numpy()
            prediction = np.squeeze(idx)
            scalar_max_val, scalar_idx = torch.max(scalar_out, 1)
            scalar_prediction = np.squeeze(scalar_idx.data.cpu().numpy())
            del X, out, idx, max_val, scalar_max_val, scalar_idx
            return prediction, scalar_prediction