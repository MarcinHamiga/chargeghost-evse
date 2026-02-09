class Session:
	def __init__(self, transaction_id: int = -1, connector_id: int = 0):
		self.transaction_id: int = transaction_id
		self.start_date: str = None
		self.connector_id: int = connector_id