import yaml


def load_config(filepath: str) -> dict:
    with open(filepath, 'r') as file:
        return yaml.safe_load(file)

def main():
    # Load the config.yaml file into the config variable
    config = load_config('config.yaml')

    # Print the config to verify it has been loaded correctly
    print(config)

if __name__ == '__main__':
    main()