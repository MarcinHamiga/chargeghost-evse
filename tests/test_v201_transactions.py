from chargeghost_evse.ocpp_adapter.transaction_manager_v201 import TransactionManagerV201


class TestTransactionManagerBegin:
	def test_first_transaction_gets_id_1(self):
		mgr = TransactionManagerV201()
		tx_id = mgr.begin_transaction(1)
		assert tx_id == "1"

	def test_second_transaction_gets_id_2(self):
		mgr = TransactionManagerV201()
		mgr.begin_transaction(1)
		tx_id = mgr.begin_transaction(2)
		assert tx_id == "2"

	def test_begin_resets_seq_no(self):
		mgr = TransactionManagerV201()
		tx_id = mgr.begin_transaction(1)
		assert mgr.get_next_seq_no(tx_id) == 0


class TestTransactionManagerSeqNo:
	def test_seq_no_increments(self):
		mgr = TransactionManagerV201()
		tx_id = mgr.begin_transaction(1)

		assert mgr.get_next_seq_no(tx_id) == 0
		assert mgr.get_next_seq_no(tx_id) == 1
		assert mgr.get_next_seq_no(tx_id) == 2

	def test_separate_transactions_have_independent_seq(self):
		mgr = TransactionManagerV201()
		tx1 = mgr.begin_transaction(1)
		tx2 = mgr.begin_transaction(2)

		assert mgr.get_next_seq_no(tx1) == 0
		assert mgr.get_next_seq_no(tx2) == 0
		assert mgr.get_next_seq_no(tx1) == 1
		assert mgr.get_next_seq_no(tx2) == 1


class TestTransactionManagerGet:
	def test_get_active_transaction(self):
		mgr = TransactionManagerV201()
		tx_id = mgr.begin_transaction(1)
		assert mgr.get_transaction_id(1) == tx_id

	def test_get_returns_none_for_unknown_evse(self):
		mgr = TransactionManagerV201()
		assert mgr.get_transaction_id(99) is None


class TestTransactionManagerEnd:
	def test_end_removes_transaction(self):
		mgr = TransactionManagerV201()
		tx_id = mgr.begin_transaction(1)
		ended = mgr.end_transaction(1)

		assert ended == tx_id
		assert mgr.get_transaction_id(1) is None

	def test_end_returns_none_for_unknown(self):
		mgr = TransactionManagerV201()
		assert mgr.end_transaction(99) is None

	def test_end_clears_seq_no(self):
		mgr = TransactionManagerV201()
		tx_id = mgr.begin_transaction(1)
		mgr.get_next_seq_no(tx_id)
		mgr.end_transaction(1)

		assert mgr.get_next_seq_no(tx_id) == 0


class TestTransactionManagerActive:
	def test_active_transactions_returns_copy(self):
		mgr = TransactionManagerV201()
		mgr.begin_transaction(1)
		active = mgr.active_transactions
		active[2] = "999"
		assert 2 not in mgr.active_transactions

	def test_active_transactions_empty(self):
		mgr = TransactionManagerV201()
		assert mgr.active_transactions == {}

	def test_multiple_active(self):
		mgr = TransactionManagerV201()
		mgr.begin_transaction(1)
		mgr.begin_transaction(2)
		assert len(mgr.active_transactions) == 2
