import progressbar
from torch.autograd import Variable
import torch
import os
from torch import cuda


class Routine(object):
    """
    this is the helper class for training and validation.
    the model object must have two properties:
    .optimizer : this is used to update the parameters
    .criterion : this is used to calculate the loss

    routine = Routine(model=model, saver_dir='ckpt/', writer=SummaryWriter('ckpt/'))
    routine.train_one_epoch(loader=train_loader)
    routine.validation(loader=dev_loader)

    saver_dir : the directory for storing parameters
    writer : SummaryWriter object, for record the loss and accuracy curve
    """

    def __init__(self, model, saver_dir, writer=None):
        self.global_step = 0
        self.epoch_step = 0
        self.record_step = 0
        self.writer = writer
        self.model = model
        self.saver_dir = saver_dir
        # the following code is used to check the model if complete
        try:
            have_optim = self.model.optimizer
            have_criterion = self.model.criterion
        except:
            raise ValueError("model must have .optimizer and .criterion property")

    def train_one_epoch(self, loader, record_n_times_per_epoch=10):

        if len(loader) < record_n_times_per_epoch:
            raise ValueError("record_n_times_per_epoch {} is larger than loader size {}"
                             .format(record_n_times_per_epoch, len(loader)))

        record_interval = len(loader) // record_n_times_per_epoch

        self.model.train()
        total_loss = cuda.FloatTensor([0.])
        total_accu = cuda.FloatTensor([0.])

        widgets = ["processing: ", progressbar.Percentage(),
                   " ", progressbar.ETA(),
                   " ", progressbar.FileTransferSpeed(),
                   ]
        bar = progressbar.ProgressBar(widgets=widgets, max_value=len(loader)).start()

        for i, batch in enumerate(loader):
            bar.update(i)
            batch_data, batch_label = batch

            batch_data = Variable(batch_data).type(torch.FloatTensor).cuda()
            batch_label = Variable(batch_label).type(torch.LongTensor).cuda()
            logits = self.model(batch_data)

            loss = self.model.criterion(logits, batch_label)

            accu = self.accuracy(logits=logits, targets=batch_label).data

            total_accu.add_(accu)
            total_loss.add_(loss.data)

            # do back-prop and update the parameters
            self.model.optimizer.zero_grad()
            loss.backward()
            self.model.optimizer.step()

            if self.writer is not None:
                if (i + 1) % record_interval == 0:
                    self.writer.add_scalar('train/loss',
                                           scalar_value=total_loss.cpu().numpy() / (i + 1),
                                           global_step=self.record_step)
                    self.writer.add_scalar('train/accu',
                                           scalar_value=total_accu.cpu().numpy() / (i + 1),
                                           global_step=self.record_step)
                    torch.save(self.model.state_dict(),
                               os.path.join(self.saver_dir,
                                            'record-step-%d-model.pkl' %
                                            self.record_step))

                    # just save the latest 5 parameters checkpoints
                    if self.record_step >= 5:
                        os.remove(os.path.join(self.saver_dir,
                                               'record-step-%d-model.pkl' %
                                               (self.record_step - 5)))

                    self.record_step += 1

        mean_loss = total_loss.cpu().numpy() / (i + 1)
        mean_accu = total_accu.cpu().numpy() / (i + 1)

        print('')
        print("training-->epoch:{},mean_loss:{}, mean_accuracy:{}".
              format(self.epoch_step, mean_loss, mean_accu))

        bar.finish()
        self.epoch_step += 1

    def validation(self, loader):

        if self.epoch_step == 0:
            record_epoch_step = 0
        else:
            record_epoch_step = self.epoch_step - 1

        self.model.eval()
        total_loss = cuda.FloatTensor([0.])
        total_accu = cuda.FloatTensor([0.])

        widgets = ["processing: ", progressbar.Percentage(),
                   " ", progressbar.ETA(),
                   " ", progressbar.FileTransferSpeed(),
                   ]
        bar = progressbar.ProgressBar(widgets=widgets, max_value=len(loader)).start()

        for i, batch in enumerate(loader):
            bar.update(i)
            batch_data, batch_label = batch

            batch_data = Variable(batch_data, volatile=True).cuda()
            batch_label = Variable(batch_label, volatile=True).cuda()
            logits = self.model(batch_data)

            loss = self.model.criterion(logits, batch_label)
            accu = self.accuracy(logits=logits, targets=batch_label).data
            total_accu.add_(accu)

            total_loss.add_(loss.data)
        #
        mean_loss = total_loss.cpu().numpy() / (i + 1)
        mean_accu = total_accu.cpu().numpy() / (i + 1)

        if self.writer is not None:
            self.writer.add_scalar('val/loss',
                                   scalar_value=mean_loss, global_step=record_epoch_step)
            self.writer.add_scalar('val/accu',
                                   scalar_value=mean_accu, global_step=record_epoch_step)
        #
        print('')
        print("validation-->epoch:{},mean_loss:{}, mean_accuracy:{}".
              format(record_epoch_step, mean_loss, mean_accu))

        bar.finish()

    def accuracy(self, logits, targets):
        """
        cal the accuracy of the predicted result
        :param logits: Variable [batch_size, num_classes]
        :param targets: Variable [batch_size]
        :return: Variable scalar
        """
        assert isinstance(logits, Variable)
        val, idx = logits.max(dim=1)
        eql = (idx == targets)
        eql = eql.type_as(logits)
        res = torch.mean(eql)
        return res
