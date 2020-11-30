REQS = httpx flask redis uwsgi pyyaml

install:
	pip3 install $(REQS)

venv:
	python3 -m venv venv; . venv/bin/activate; pip3 install $(REQS);

clean:
	rm -rf venv __pycache__
