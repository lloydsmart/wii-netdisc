.PHONY: stock-dip-baseline
stock-dip-baseline:
	python3 -B -m scripts.stock_dip_build

.PHONY: experimental-dip-sizing
experimental-dip-sizing:
	python3 -B -m scripts.experimental_dip_build
