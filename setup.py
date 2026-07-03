from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

setup(
	name="gfct_customer_statement",
	version="0.0.1",
	description="GFCT Customer Statement Report",
	author="GFCT",
	author_email="info@gfct.ae",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)
