.PHONY: dev install test cdk-synth

dev:
	python app.py

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -q

cdk-synth:
	cd infra/cdk && cdk synth
