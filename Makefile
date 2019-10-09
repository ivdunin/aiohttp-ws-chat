%:
	@:

start_rmq:
	docker-compose -f docker-compose.yml up -d

stop_rmq:
	docker-compose down

init_virtualenv:
	python -m venv venv
	. venv/bin/activate; pip install -r requirements.txt

run_app: start_rmq init_virtualenv
	. venv/bin/activate; \
	python app.py

clear_venv:
	rm -rf ./venv
