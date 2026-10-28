class ScryError(Exception):
    pass


class InvalidDocumentId(ScryError):
    pass


class DocumentNotFound(ScryError):
    def __init__(self, doc_id: str) -> None:
        super().__init__(f"document not found: {doc_id}")
        self.doc_id = doc_id
