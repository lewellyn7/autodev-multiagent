class ModelAgent:
    def __init__(self):
        self.models = []  # List to store models

    def add_model(self, model):
        """
        Adds a model to the model management system.
        :param model: The model to be added.
        """
        self.models.append(model)
        print(f"Model added: {model}")

    def fetch_models_from_source(self, source):
        """
        Fetches models from a given source.
        :param source: The source to fetch models from.
        """
        # Here you would implement the logic to fetch models
        print(f"Fetching models from {source}")
        # For now, we just return an empty list
        return []

    def delete_model(self, model):
        """
        Deletes a model from the model management system.
        :param model: The model to be deleted.
        """
        if model in self.models:
            self.models.remove(model)
            print(f"Model deleted: {model}")
        else:
            print(f"Model not found: {model}")
