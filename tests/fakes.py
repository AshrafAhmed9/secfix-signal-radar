class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._json
