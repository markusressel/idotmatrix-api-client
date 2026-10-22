# This Makefile is a proxy for the Justfile.
# It allows you to run `make <target>` which will be forwarded to `just <target>`.

.PHONY: default
default:
	@just --list

.PHONY: %
%:
	@just $@
