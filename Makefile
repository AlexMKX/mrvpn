all: develop

install-deps:
	./venv/bin/pip install -r requirements.txt

create-venv:
	 rm -rf venv
	 virtualenv -p python3 venv

develop: create-venv install-deps
