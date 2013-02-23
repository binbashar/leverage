from setuptools import setup
import pynt
setup(
    name="pynt",
    version= pynt.__version__,
    author="Raghunandan Rao",
    author_email="r.raghunandan@gmail.com",
    url= pynt.__contact__, 
    packages=["pynt"],
    entry_points =  {'console_scripts': ['pynt=pynt:main']}, 
    license="MIT License",
    description="Lightweight Python Build Tool.",
    long_description=open("README.rst").read()+"\n"+open("CHANGES.rst").read()
)
