.PHONY: server client

server:
	npm run watch

client:
	python client/app.py
