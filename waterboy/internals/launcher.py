import argparse

from waterboy.internals.project_config import ProjectConfig
from waterboy.internals.model_config import ModelConfig


def main():
    """ Paperboy entry point - parse the arguments and run a command """
    parser = argparse.ArgumentParser(description='Paperboy deep learning launcher')

    parser.add_argument('command', metavar='COMMAND', help='A command to run')
    parser.add_argument('config', metavar='FILENAME', help='Configuration file for the run')
    parser.add_argument('-r', '--run_number', default=0, help="A run number")
    parser.add_argument('-d', '--device', default='cuda', help="A device to run the model on")

    # TODO(jerry) - override configutation = -o train.batch_size=16

    args = parser.parse_args()

    project_config = ProjectConfig(args.config)
    model_config = ModelConfig(args.config, args.run_number, project_config, device=args.device)

    model_config.banner(args.command)
    model_config.run_command(args.command)
    model_config.quit_banner()


if __name__ == '__main__':
    main()