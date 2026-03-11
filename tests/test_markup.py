from chargeghost_evse.util.markup import strip_markup


class TestStripMarkup:
	def test_strips_rich_tags(self):
		assert strip_markup("[yellow]Engine:[/yellow] started") == "Engine: started"

	def test_preserves_plain_text(self):
		assert strip_markup("no tags here") == "no tags here"

	def test_strips_nested_tags(self):
		assert strip_markup("[bold][red]Error[/red][/bold]") == "Error"

	def test_empty_string(self):
		assert strip_markup("") == ""
