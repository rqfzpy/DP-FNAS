import torch
import torch.nn as nn
import os, shutil
import numpy as np
import logging


def get_logger(file_path):
    """ Make python logger """
    # [!] Since tensorboardX use default logger (e.g. logging.info()), we should use custom logger
    logger = logging.getLogger('darts')
    log_format = '%(asctime)s | %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%m/%d %H:%M:%S %p')
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.INFO)

    return logger

def repackage_hidden(h):
    """Wraps hidden states in new Tensors, to detach them from their history."""
    if isinstance(h, torch.Tensor):
        return h.detach()
    else:
        return tuple(repackage_hidden(v) for v in h)


def batchify(data, bsz, args):
    nbatch = data.size(0) // bsz
    data = data.narrow(0, 0, nbatch * bsz)
    data = data.view(bsz, -1).t().contiguous()
    print(data.size())
    data = data.cuda()
    return data


def get_batch(source, i, args, seq_len=None, evaluation=False):
    seq_len = min(seq_len if seq_len else args.bptt, len(source) - 1 - i)
    data = source[i:i+seq_len].detach() if evaluation else source[i:i+seq_len]
    target = source[i+1:i+1+seq_len]
    return data, target


def create_exp_dir(path, scripts_to_save=None):
    if not os.path.exists(path):
        os.mkdir(path)

    print('Experiment dir : {}'.format(path))
    if scripts_to_save is not None:
        if not os.path.exists(os.path.join(path, 'scripts')):
            os.mkdir(os.path.join(path, 'scripts'))
            for script in scripts_to_save:
                dst_file = os.path.join(path, 'scripts', os.path.basename(script))
                shutil.copyfile(script, dst_file)


def save_checkpoint(model, optimizer, epoch, path, finetune=False, dist_name=None):
    if finetune:
        middle_name = 'finetune_'
    else:
        middle_name = ''
    if dist_name is not None:
        model_name = dist_name + '-' + middle_name + 'model.pt'
        opt_name = dist_name + '-' + middle_name + 'optimizer.pt'
        misc_name = dist_name + '-' + 'misc.pt'

    torch.save(model, os.path.join(path, model_name))
    torch.save(optimizer.state_dict(), os.path.join(path, opt_name))
    torch.save({'epoch': epoch+1}, os.path.join(path, misc_name))


def embedded_dropout(embed, words, dropout=0.1, scale=None):
    if dropout:
        mask = embed.weight.data.new().resize_((embed.weight.size(0), 1)).bernoulli_(1 - dropout).expand_as(embed.weight) / (1 - dropout)
        masked_embed_weight = mask * embed.weight
    else:
        masked_embed_weight = embed.weight
    if scale:
        masked_embed_weight = scale.expand_as(masked_embed_weight) * masked_embed_weight

    padding_idx = embed.padding_idx
    if padding_idx is None:
        padding_idx = -1
    # X = embed._backend.Embedding.apply(words, masked_embed_weight,
    #     padding_idx, embed.max_norm, embed.norm_type,
    #     embed.scale_grad_by_freq, embed.sparse
    # )
    X = nn.functional.embedding(words, masked_embed_weight,
        padding_idx, embed.max_norm, embed.norm_type,
        embed.scale_grad_by_freq, embed.sparse
    )
    return X


class LockedDropout(nn.Module):
    def __init__(self):
        super(LockedDropout, self).__init__()

    def forward(self, x, dropout=0.5):
        if not self.training or not dropout:
            return x
        m = x.data.new(1, x.size(1), x.size(2)).bernoulli_(1 - dropout)
        mask = m.div_(1 - dropout).detach()
        mask = mask.expand_as(x)
        return mask * x


def mask2d(B, D, keep_prob):
    m = torch.floor(torch.rand(B, D) + keep_prob) / keep_prob
    m = m.requires_grad_(False).cuda()
    return m

