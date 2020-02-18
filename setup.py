"""
OpenBanking v1.0.0
Mock API for banking services

"""

# Always prefer setuptools over distutils
from setuptools import setup
# To use a consistent encoding
import sys
from distutils.core import setup
from Cython.Build import cythonize
from os import path

here = path.abspath(path.dirname(__file__))


setup(
    name='openbanking',
    version='1.0.0',
    description='Mock API for banking services',
    long_description='',
    url='',
    license='Apache-2.0',
    ext_modules=cythonize(
        "utils.pyx",
        compiler_directives={'language_level': sys.version_info[0]}
    ), requires=['Cython']

)
