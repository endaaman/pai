.PHONY: server client

server:
	npm run watch

client:
	pipenv run client
