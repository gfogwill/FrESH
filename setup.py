from setuptools import find_packages, setup
from src import __version__

setup(
    name='src',
    packages=find_packages(),
    version=__version__,
    description='Th',
    author='gfogwill',
    license='MIT',
)
