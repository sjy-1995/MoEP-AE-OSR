import os
import sys
import time
import numpy as np
import torch

try:
    _, term_width = os.popen('stty size', 'r').read().split()
    term_width = int(term_width)
except:
    term_width = 84

TOTAL_BAR_LENGTH = 65.
last_time = time.time()
begin_time = last_time


def progress_bar(current, total, msg=None):
    global last_time, begin_time
    if current == 0:
        begin_time = time.time()  # Reset for new bar.

    cur_len = int(TOTAL_BAR_LENGTH*current/total)
    rest_len = int(TOTAL_BAR_LENGTH - cur_len) - 1

    sys.stdout.write(' [')
    for i in range(cur_len):
        sys.stdout.write('=')
    sys.stdout.write('>')
    for i in range(rest_len):
        sys.stdout.write('.')
    sys.stdout.write(']')

    cur_time = time.time()
    step_time = cur_time - last_time
    last_time = cur_time
    tot_time = cur_time - begin_time

    L = []
    L.append('  Step: %s' % format_time(step_time))
    L.append(' | Tot: %s' % format_time(tot_time))
    if msg:
        L.append(' | ' + msg)

    msg = ''.join(L)
    sys.stdout.write(msg)
    for i in range(term_width-int(TOTAL_BAR_LENGTH)-len(msg)-3):
        sys.stdout.write(' ')

    # Go back to the center of the bar.
    for i in range(term_width-int(TOTAL_BAR_LENGTH/2)+2):
        sys.stdout.write('\b')
    sys.stdout.write(' %d/%d ' % (current+1, total))

    if current < total-1:
        sys.stdout.write('\r')
    else:
        sys.stdout.write('\n')
    sys.stdout.flush()


def format_time(seconds):
    days = int(seconds / 3600/24)
    seconds = seconds - days*3600*24
    hours = int(seconds / 3600)
    seconds = seconds - hours*3600
    minutes = int(seconds / 60)
    seconds = seconds - minutes*60
    secondsf = int(seconds)
    seconds = seconds - secondsf
    millis = int(seconds*1000)

    f = ''
    i = 1
    if days > 0:
        f += str(days) + 'D'
        i += 1
    if hours > 0 and i <= 2:
        f += str(hours) + 'h'
        i += 1
    if minutes > 0 and i <= 2:
        f += str(minutes) + 'm'
        i += 1
    if secondsf > 0 and i <= 2:
        f += str(secondsf) + 's'
        i += 1
    if millis > 0 and i <= 2:
        f += str(millis) + 'ms'
        i += 1
    if f == '':
        f = '0ms'
    return f


# def find_anchor_means(net, mapping, datasetName, trial_num, cfg, only_correct=False):
#     ''' Tests data and fits a multivariate gaussian to each class' logits.
#         If dataloaderFlip is not None, also test with flipped images.
#         Returns means and covariances for each class. '''
#     # find gaussians for each class
#     if datasetName == 'MNIST' or datasetName == "SVHN":
#         loader, _ = dataHelper.get_anchor_loaders(datasetName, trial_num, cfg)
#         logits, labels = gather_outputs(net, mapping, loader, only_correct=only_correct, num_classes=cfg['num_known_classes'])
#     else:
#         loader, loaderFlipped = dataHelper.get_anchor_loaders(datasetName, trial_num, cfg)
#         logits, labels = gather_outputs(net, mapping, loader, loaderFlipped, only_correct=only_correct, num_classes=cfg['num_known_classes'])
#
#     num_classes = cfg['num_known_classes']
#     means = [None for i in range(num_classes)]
#
#     for cl in range(num_classes):
#         x = logits[labels == cl]
#         x = np.squeeze(x)
#         means[cl] = np.mean(x, axis=0)
#
#     return means


def find_anchor_means(net, mapping, dataloader, cfg, only_correct=False):
    ''' Tests data and fits a multivariate gaussian to each class' logits.
        If dataloaderFlip is not None, also test with flipped images.
        Returns means and covariances for each class. '''
    # find gaussians for each class
    mus, sigmaps, ps, labels = gather_outputs_parameters(net, mapping, dataloader, None, only_correct=only_correct, num_classes=cfg['num_known_classes'])

    num_classes = cfg['num_known_classes']
    mu_means = [None for i in range(num_classes)]
    sigmap_means = [None for i in range(num_classes)]
    p_means = [None for i in range(num_classes)]

    for cl in range(num_classes):
        x = mus[labels == cl]
        x = np.squeeze(x)
        mu_means[cl] = np.mean(x, axis=0)
        x = sigmaps[labels == cl]
        x = np.squeeze(x)
        sigmap_means[cl] = np.mean(x, axis=0)
        x = ps[labels == cl]
        x = np.squeeze(x)
        p_means[cl] = np.mean(x, axis=0)

    return mu_means, sigmap_means, p_means


def SoftmaxTemp(logits, T=1):
    num = torch.exp(logits/T) 
    denom = torch.sum(torch.exp(logits/T), 1).unsqueeze(1) 
    return num/denom 


def gather_outputs_parameters(net, mapping, dataloader, dataloaderFlip=None, data_idx=0, calculate_scores=False, unknown=False, only_correct=False, num_classes=20):
    ''' Tests data and returns outputs and their ground truth labels.
        data_idx        0 returns logits, 1 returns distances to anchors
        use_softmax     True to apply softmax
        unknown         True if an unknown dataset
        only_correct    True to filter for correct classifications as per logits
    '''
    X = []
    y = []
    mus = []
    sigmaps = []
    ps = []

    if calculate_scores:
        softmax = torch.nn.Softmax(dim=1)

    for i, data in enumerate(dataloader):
        images, labels = data
        images = images.cuda()

        if images.shape[1] != 3:
            images = images.repeat(1, 3, 1, 1)

        if unknown:
            # targets = labels
            targets = torch.zeros_like(labels)
        else:
            # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
            targets = torch.Tensor([mapping[x] for x in labels]).long()
            # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

        target_en = torch.Tensor(targets.shape[0], num_classes)
        target_en.zero_()
        target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
        target_en = target_en.cuda()
        targets = targets.cuda()

        outputs = net(images, target_en)
        logits = outputs[0]   # outLinear1
        mu = outputs[2]
        sigmap = outputs[3]
        p = outputs[4]

        if only_correct:
            if data_idx == 0:
                _, predicted = torch.max(logits, 1)
            else:
                _, predicted = torch.min(distances, 1)
            
            mask = predicted == targets
            logits = logits[mask]
            distances = distances[mask]
            targets = targets[mask]

        if calculate_scores:
            # softmin = softmax(-distances)
            # invScores = 1-softmin
            # scores = distances*invScores
            scores = softmax(distances)
        else:
            if data_idx == 0:
                scores = logits
            if data_idx == 1:
                scores = distances

        X += scores.cpu().detach().tolist()
        y += targets.cpu().tolist()
        mus += mu.cpu().tolist()
        sigmaps += sigmap.cpu().tolist()
        ps += p.cpu().tolist()

    if dataloaderFlip is not None:
        for i, data in enumerate(dataloaderFlip):
            images, labels = data
            images = images.cuda()

            if images.shape[1] != 3:
                images = images.repeat(1, 3, 1, 1)

            if unknown:
                # targets = labels
                targets = torch.zeros_like(labels)
            else:
                # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
                targets = torch.Tensor([mapping[x] for x in labels]).long()
                # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

            target_en = torch.Tensor(targets.shape[0], num_classes)
            target_en.zero_()
            target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
            target_en = target_en.cuda()
            targets = targets.cuda()

            outputs = net(images, target_en)
            logits = outputs[0]
            distances = outputs[1]
            # logits = outputs[2]
            # distances = outputs[3]

            if only_correct:
                if data_idx == 0:
                    _, predicted = torch.max(logits, 1)
                else:
                    _, predicted = torch.min(distances, 1)
                mask = predicted == targets
                logits = logits[mask]
                distances = distances[mask]
                targets = targets[mask]

            if calculate_scores:
                # softmin = softmax(-distances)
                # invScores = 1-softmin
                # scores = distances*invScores
                scores = softmax(distances)
            else:
                if data_idx == 0:
                    scores = logits
                if data_idx == 1:
                    scores = distances

            X += scores.cpu().detach().tolist()
            y += targets.cpu().tolist()

    X = np.asarray(X)
    y = np.asarray(y)
    mus = np.asarray(mus)
    sigmaps = np.asarray(sigmaps)
    ps = np.asarray(ps)

    return mus, sigmaps, ps, y


def gather_outputs(net, mapping, dataloader, dataloaderFlip=None, data_idx=0, calculate_scores=False, unknown=False, only_correct=False, num_classes=20):
    ''' Tests data and returns outputs and their ground truth labels.
        data_idx        0 returns logits, 1 returns distances to anchors
        use_softmax     True to apply softmax
        unknown         True if an unknown dataset
        only_correct    True to filter for correct classifications as per logits
    '''
    X = []
    y = []

    if calculate_scores:
        softmax = torch.nn.Softmax(dim=1)

    for i, data in enumerate(dataloader):
        images, labels = data
        images = images.cuda()

        if images.shape[1] != 3:
            images = images.repeat(1, 3, 1, 1)

        if unknown:
            # targets = labels
            targets = torch.zeros_like(labels)
        else:
            # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
            targets = torch.Tensor([mapping[x] for x in labels]).long()
            # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

        target_en = torch.Tensor(targets.shape[0], num_classes)
        target_en.zero_()
        target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
        target_en = target_en.cuda()
        targets = targets.cuda()

        outputs = net(images, target_en)
        logits = outputs[0]   # outLinear1

        if only_correct:
            if data_idx == 0:
                _, predicted = torch.max(logits, 1)
            else:
                _, predicted = torch.min(distances, 1)

            mask = predicted == targets
            logits = logits[mask]
            distances = distances[mask]
            targets = targets[mask]

        if calculate_scores:
            # softmin = softmax(-distances)
            # invScores = 1-softmin
            # scores = distances*invScores
            scores = softmax(distances)
        else:
            if data_idx == 0:
                scores = logits
            if data_idx == 1:
                scores = distances

        X += scores.cpu().detach().tolist()
        y += targets.cpu().tolist()

    if dataloaderFlip is not None:
        for i, data in enumerate(dataloaderFlip):
            images, labels = data
            images = images.cuda()

            if images.shape[1] != 3:
                images = images.repeat(1, 3, 1, 1)

            if unknown:
                # targets = labels
                targets = torch.zeros_like(labels)
            else:
                # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
                targets = torch.Tensor([mapping[x] for x in labels]).long()
                # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

            target_en = torch.Tensor(targets.shape[0], num_classes)
            target_en.zero_()
            target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
            target_en = target_en.cuda()
            targets = targets.cuda()

            outputs = net(images, target_en)
            logits = outputs[0]
            distances = outputs[1]
            # logits = outputs[2]
            # distances = outputs[3]

            if only_correct:
                if data_idx == 0:
                    _, predicted = torch.max(logits, 1)
                else:
                    _, predicted = torch.min(distances, 1)
                mask = predicted == targets
                logits = logits[mask]
                distances = distances[mask]
                targets = targets[mask]

            if calculate_scores:
                # softmin = softmax(-distances)
                # invScores = 1-softmin
                # scores = distances*invScores
                scores = softmax(distances)
            else:
                if data_idx == 0:
                    scores = logits
                if data_idx == 1:
                    scores = distances

            X += scores.cpu().detach().tolist()
            y += targets.cpu().tolist()

    X = np.asarray(X)
    y = np.asarray(y)

    return X, y


def gather_outputs_OOD(net, dataloader, dataloaderFlip=None, data_idx=0, calculate_scores=False, unknown=False, only_correct=False, num_classes=20):
    ''' Tests data and returns outputs and their ground truth labels.
        data_idx        0 returns logits, 1 returns distances to anchors
        use_softmax     True to apply softmax
        unknown         True if an unknown dataset
        only_correct    True to filter for correct classifications as per logits
    '''
    X = []
    y = []

    if calculate_scores:
        softmax = torch.nn.Softmax(dim=1)

    for i, data in enumerate(dataloader):
        images, labels = data
        images = images.cuda()

        if images.shape[1] != 3:
            images = images.repeat(1, 3, 1, 1)

        if unknown:
            # targets = labels
            targets = torch.zeros_like(labels)
        else:
            # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
            # targets = torch.Tensor([mapping[x] for x in labels]).long()
            targets = labels.long()
            # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

        target_en = torch.Tensor(targets.shape[0], num_classes)
        target_en.zero_()
        target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
        target_en = target_en.cuda()
        targets = targets.cuda()

        outputs = net(images, target_en)
        logits = outputs[0]   # outLinear1

        if only_correct:
            if data_idx == 0:
                _, predicted = torch.max(logits, 1)
            else:
                _, predicted = torch.min(distances, 1)

            mask = predicted == targets
            logits = logits[mask]
            distances = distances[mask]
            targets = targets[mask]

        if calculate_scores:
            # softmin = softmax(-distances)
            # invScores = 1-softmin
            # scores = distances*invScores
            scores = softmax(distances)
        else:
            if data_idx == 0:
                scores = logits
            if data_idx == 1:
                scores = distances

        X += scores.cpu().detach().tolist()
        y += targets.cpu().tolist()

    # if dataloaderFlip is not None:
    #     for i, data in enumerate(dataloaderFlip):
    #         images, labels = data
    #         images = images.cuda()
    #
    #         if images.shape[1] != 3:
    #             images = images.repeat(1, 3, 1, 1)
    #
    #         if unknown:
    #             # targets = labels
    #             targets = torch.zeros_like(labels)
    #         else:
    #             # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
    #             targets = torch.Tensor([mapping[x] for x in labels]).long()
    #             # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()
    #
    #         target_en = torch.Tensor(targets.shape[0], num_classes)
    #         target_en.zero_()
    #         target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
    #         target_en = target_en.cuda()
    #         targets = targets.cuda()
    #
    #         outputs = net(images, target_en)
    #         logits = outputs[0]
    #         distances = outputs[1]
    #         # logits = outputs[2]
    #         # distances = outputs[3]
    #
    #         if only_correct:
    #             if data_idx == 0:
    #                 _, predicted = torch.max(logits, 1)
    #             else:
    #                 _, predicted = torch.min(distances, 1)
    #             mask = predicted == targets
    #             logits = logits[mask]
    #             distances = distances[mask]
    #             targets = targets[mask]
    #
    #         if calculate_scores:
    #             # softmin = softmax(-distances)
    #             # invScores = 1-softmin
    #             # scores = distances*invScores
    #             scores = softmax(distances)
    #         else:
    #             if data_idx == 0:
    #                 scores = logits
    #             if data_idx == 1:
    #                 scores = distances
    #
    #         X += scores.cpu().detach().tolist()
    #         y += targets.cpu().tolist()

    X = np.asarray(X)
    y = np.asarray(y)

    return X, y


def gather_outputs_samples(net, mapping, dataloader, dataloaderFlip=None, data_idx=0, calculate_scores=False, unknown=False, only_correct=False, num_classes=20):
    ''' Tests data and returns outputs and their ground truth labels.
        data_idx        0 returns logits, 1 returns distances to anchors
        use_softmax     True to apply softmax
        unknown         True if an unknown dataset
        only_correct    True to filter for correct classifications as per logits
    '''
    X = []
    y = []

    if calculate_scores:
        softmax = torch.nn.Softmax(dim=1)

    for i, data in enumerate(dataloader):
        images, labels = data
        images = images.cuda()

        if images.shape[1] != 3:
            images = images.repeat(1, 3, 1, 1)

        if unknown:
            # targets = labels
            targets = torch.zeros_like(labels)
        else:
            # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
            targets = torch.Tensor([mapping[x] for x in labels]).long()
            # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

        target_en = torch.Tensor(targets.shape[0], num_classes)
        target_en.zero_()
        target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
        target_en = target_en.cuda()
        targets = targets.cuda()

        outputs = net(images, target_en)
        # logits = outputs[0]   # outLinear1
        logits = outputs   # samples_latent

        if only_correct:
            if data_idx == 0:
                _, predicted = torch.max(logits, 1)
            else:
                _, predicted = torch.min(distances, 1)

            mask = predicted == targets
            logits = logits[mask]
            distances = distances[mask]
            targets = targets[mask]

        if calculate_scores:
            # softmin = softmax(-distances)
            # invScores = 1-softmin
            # scores = distances*invScores
            scores = softmax(distances)
        else:
            if data_idx == 0:
                scores = logits
            if data_idx == 1:
                scores = distances

        X += scores.cpu().detach().tolist()
        y += targets.cpu().tolist()

    if dataloaderFlip is not None:
        for i, data in enumerate(dataloaderFlip):
            images, labels = data
            images = images.cuda()

            if images.shape[1] != 3:
                images = images.repeat(1, 3, 1, 1)

            if unknown:
                # targets = labels
                targets = torch.zeros_like(labels)
            else:
                # targets = torch.Tensor([mapping[x] for x in labels]).long().cuda()
                targets = torch.Tensor([mapping[x] for x in labels]).long()
                # targets = torch.Tensor([mapping[x] for x in float(labels)]).long().cuda()

            target_en = torch.Tensor(targets.shape[0], num_classes)
            target_en.zero_()
            target_en.scatter_(1, targets.view(-1, 1), 1)  # one-hot encoding
            target_en = target_en.cuda()
            targets = targets.cuda()

            outputs = net(images, target_en)
            logits = outputs[0]
            distances = outputs[1]
            # logits = outputs[2]
            # distances = outputs[3]

            if only_correct:
                if data_idx == 0:
                    _, predicted = torch.max(logits, 1)
                else:
                    _, predicted = torch.min(distances, 1)
                mask = predicted == targets
                logits = logits[mask]
                distances = distances[mask]
                targets = targets[mask]

            if calculate_scores:
                # softmin = softmax(-distances)
                # invScores = 1-softmin
                # scores = distances*invScores
                scores = softmax(distances)
            else:
                if data_idx == 0:
                    scores = logits
                if data_idx == 1:
                    scores = distances

            X += scores.cpu().detach().tolist()
            y += targets.cpu().tolist()

    X = np.asarray(X)
    y = np.asarray(y)

    return X, y


