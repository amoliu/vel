import os
import pathlib
import re
import torch
import typing

import waterboy.api.base as base

from waterboy.api import ModelConfig, EpochInfo
from waterboy.api.base import Model
from .strategy.checkpoint_strategy import CheckpointStrategy


class ClassicStorage(base.Storage):
    """ Model and metric persistence - classic implementation """

    def __init__(self, model_config: ModelConfig, checkpoint_strategy: CheckpointStrategy, backend, streaming=None):
        self.model_config = model_config
        self.backend = backend
        self.streaming = streaming or []
        self.checkpoint_strategy = checkpoint_strategy

        self.cleaned = False

    def restore(self, hidden_state):
        """ Restore optimizer and callbacks from hidden state """
        super().restore(hidden_state)
        self.checkpoint_strategy.restore(hidden_state)

    def resume_learning(self, model) -> (int, typing.Union[dict, None]):
        """ Resume training a model from a previously stored session """
        last_epoch = self._persisted_last_epoch()

        if last_epoch > 0:
            try:
                model.load_state_dict(torch.load(self.checkpoint_filename(last_epoch)))
                hidden_state = torch.load(self.checkpoint_hidden_filename(last_epoch))
            except FileNotFoundError:
                # If any of files does not exist, just ignore the checkpoint
                return 0, None

            self.restore(hidden_state)

            return last_epoch, hidden_state
        else:
            return last_epoch, None

    def get_frame(self):
        """ Get a frame of metrics from backend """
        return self.backend.get_frame()

    def clean(self, global_epoch_idx):
        """ Clean old checkpoints """
        if self.cleaned:
            return

        self.cleaned = True
        self.backend.clean(global_epoch_idx)

    def checkpoint(self, epoch_info: EpochInfo, model: Model, state_dict: dict=None):
        """ When epoch is done, we persist the training state """
        state_dict = state_dict if state_dict is not None else {}

        self.clean(epoch_info.global_epoch_idx)

        self._make_sure_dir_exists()

        # Checkpoint latest
        torch.save(model.state_dict(), self.checkpoint_filename(epoch_info.global_epoch_idx))

        hidden_state = state_dict.copy()

        if epoch_info.optimizer is not None:
            hidden_state['optimizer'] = epoch_info.optimizer.state_dict()

        for callback in epoch_info.callbacks:
            callback.write_state_dict(hidden_state)

        self.checkpoint_strategy.write_state_dict(hidden_state)

        torch.save(hidden_state, self.checkpoint_hidden_filename(epoch_info.global_epoch_idx))

        if epoch_info.global_epoch_idx > 1 and self.checkpoint_strategy.should_delete_previous_checkpoint(epoch_info.global_epoch_idx):
            prev_epoch_idx = epoch_info.global_epoch_idx - 1

            os.remove(self.checkpoint_filename(prev_epoch_idx))
            os.remove(self.checkpoint_hidden_filename(prev_epoch_idx))

        if self.checkpoint_strategy.should_store_best_checkpoint(epoch_info.global_epoch_idx, epoch_info.result):
            best_checkpoint_idx = self.checkpoint_strategy.current_best_checkpoint_idx

            if best_checkpoint_idx is not None:
                os.remove(self.checkpoint_best_filename(best_checkpoint_idx))

            torch.save(model.state_dict(), self.checkpoint_best_filename(epoch_info.global_epoch_idx))

            self.checkpoint_strategy.store_best_checkpoint_idx(epoch_info.global_epoch_idx)

        self.backend.store(epoch_info.result)

    def streaming_callbacks(self) -> list:
        """ Lift of callbacks for live streaming results """
        return self.streaming

    ####################################################################################################################
    # Filename helpers
    def checkpoint_filename(self, epoch_idx) -> str:
        """ Return checkpoint filename for this model """
        return self.model_config.checkpoint_dir('checkpoint_{:08}.data'.format(epoch_idx))

    def checkpoint_best_filename(self, epoch_idx) -> str:
        """ Return checkpoint filename for this model - best version """
        return self.model_config.checkpoint_dir('checkpoint_best_{:08}.data'.format(epoch_idx))

    def checkpoint_hidden_filename(self, epoch_idx) -> str:
        """ Return checkpoint filename for this model - hidden state """
        return self.model_config.checkpoint_dir('checkpoint_hidden_{:08}.data'.format(epoch_idx))

    ####################################################################################################################
    # Internal interface
    def _persisted_last_epoch(self) -> int:
        """ Return number of last epoch already calculated """
        epoch_number = 0
        self._make_sure_dir_exists()

        for x in os.listdir(self.model_config.checkpoint_dir()):
            match = re.match('checkpoint_(\\d+)\\.data', x)
            if match:
                idx = int(match[1])

                if idx > epoch_number:
                    epoch_number = idx

        return epoch_number

    def _make_sure_dir_exists(self):
        """ Make sure directory exists """
        filename = self.model_config.checkpoint_dir()
        pathlib.Path(filename).mkdir(parents=True, exist_ok=True)


def create(model_config, backend, checkpoint_strategy, streaming=None):
    """ Waterboy creation function """
    return ClassicStorage(
        model_config=model_config,
        backend=backend,
        checkpoint_strategy=checkpoint_strategy,
        streaming=streaming
    )
