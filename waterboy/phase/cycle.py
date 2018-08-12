import numpy as np

import waterboy.api.base as base
import waterboy.util.intepolate as interp
import waterboy.util.module_util as mu

from waterboy.api import BatchInfo


class CycleCallback(base.Callback):
    """ A callback that manages setting the proper learning rate """

    def __init__(self, optimizer, max_lr, min_lr, cycles, cycle_len=1, cycle_mult=1, init_iter=0, init_lr=0, interpolate='linear'):
        self.max_lr = max_lr
        self.min_lr = min_lr

        self.cycles = cycles
        self.cycle_len = cycle_len
        self.cycle_mult = cycle_mult

        self.init_iter = init_iter
        self.init_lr = init_lr

        if cycle_mult > 1:
            self.epochs = self.cycle_len * (self.cycle_mult ** self.cycles - 1) // (self.cycle_mult - 1)
        else:
            self.epochs = self.cycle_mult * self.cycles

        self.optimizer = optimizer
        self.interpolate = interpolate

        # self.current_cycle = None
        self.cycle_dict, self.cycle_lengths, self.cycle_starts = self._init_cycle_dict()

    def _init_cycle_dict(self):
        """ Populate a cycle dict """
        dict_arr = np.zeros(self.epochs, dtype=int)
        length_arr = np.zeros(self.epochs, dtype=int)
        start_arr = np.zeros(self.epochs, dtype=int)

        c_len = self.cycle_len
        idx = 0

        for i in range(self.cycles):
            current_start = idx
            for j in range(c_len):
                dict_arr[idx] = i
                length_arr[idx] = c_len
                start_arr[idx] = current_start
                idx += 1

            c_len *= self.cycle_mult

        return dict_arr, length_arr, start_arr

    def on_batch_begin(self, batch_info: BatchInfo):
        """ Set proper learning rate """
        cycle_length = self.cycle_lengths[batch_info.local_epoch_number - 1]
        cycle_start = self.cycle_starts[batch_info.local_epoch_number - 1]

        numerator = (batch_info.local_epoch_number - cycle_start - 1) * batch_info.batches_per_epoch + batch_info.batch_number
        denominator = cycle_length * batch_info.batches_per_epoch

        interpolation_number = numerator / denominator

        if cycle_start == 0 and numerator < self.init_iter:
            lr = self.init_lr
        else:
            if isinstance(self.max_lr, list):
                lr = [interp.interpolate_single(max_lr, min_lr, interpolation_number, how=self.interpolate) for max_lr, min_lr in zip(self.max_lr, self.min_lr)]
            else:
                lr = interp.interpolate_single(self.max_lr, self.min_lr, interpolation_number, how=self.interpolate)

        self.set_lr(lr)

    def set_lr(self, lr):
        """ Set a learning rate for the optimizer """
        if isinstance(lr, list):
            for group_lr, param_group in zip(lr, self.optimizer.param_groups):
                param_group['lr'] = group_lr
        else:
            for param_group in self.optimizer.param_groups:
                param_group['lr'] = lr


class CyclePhase(base.TrainPhase):
    """ Most generic phase of training """

    def __init__(self, optimizer_factory, max_lr, min_lr, cycles, cycle_len=1, cycle_mult=1, interpolate='linear',
                 init_lr=0, init_iter=0, freeze=False):
        self.max_lr = max_lr
        self.min_lr = min_lr

        self.cycles = cycles
        self.cycle_len = cycle_len
        self.cycle_mult = cycle_mult

        if cycle_mult > 1:
            self.epochs = self.cycle_len * (self.cycle_mult ** self.cycles - 1) // (self.cycle_mult - 1)
        else:
            self.epochs = self.cycle_mult * self.cycles

        self.interpolate = interpolate

        self.init_iter = init_iter
        self.init_lr = init_lr

        self.optimizer_factory = optimizer_factory
        self.freeze = freeze

        self._optimizer_instance = None
        self._source = None

        self.special_callback = None

    @property
    def number_of_epochs(self) -> int:
        return self.epochs

    def set_up_phase(self, training_info, model, source):
        """ Prepare the phase for learning """
        # To parameter groups handles properly filtering parameters that don't require gradient
        parameter_groups = mu.to_parameter_groups(model.get_layer_groups())
        self._optimizer_instance = self.optimizer_factory.instantiate(parameter_groups)
        self._source = source

        self.special_callback = CycleCallback(
            self._optimizer_instance,
            max_lr=self.max_lr, min_lr=self.min_lr, cycles=self.cycles,
            cycle_len=self.cycle_len, cycle_mult=self.cycle_mult, interpolate=self.interpolate,
            init_iter=self.init_iter, init_lr=self.init_lr
        )

        return self._optimizer_instance

    def execute_epoch(self, epoch_info, learner):
        """ Prepare the phase for learning """
        # Add special callback for this epoch
        epoch_info.callbacks = [self.special_callback] + epoch_info.callbacks
        learner.run_epoch(epoch_info, self._source)


def create(optimizer, max_lr, min_lr, cycles, cycle_len=1, cycle_mult=1, interpolate='linear', init_lr=0, init_iter=0):
    """ Waterboy creation function """
    return CyclePhase(
        max_lr=max_lr,
        min_lr=min_lr,
        cycles=cycles,
        cycle_len=cycle_len,
        cycle_mult=cycle_mult,
        interpolate=interpolate,
        optimizer_factory=optimizer,
        init_lr=init_lr,
        init_iter=init_iter,
    )
