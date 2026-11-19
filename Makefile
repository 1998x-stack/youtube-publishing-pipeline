.PHONY: setup test lint validate status
setup:
	python -m pip install -e '.[dev]'
test:
	pytest -q
lint:
	ruff check src tests
validate:
	ytp validate
status:
	ytp status
