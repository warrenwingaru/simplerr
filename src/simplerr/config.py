class Config(dict):
    def __init__(self, defaults: dict = None):
        super().__init__(defaults or {})