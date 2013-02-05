from setuptools import setup

setup(
    name="pynt",
    version="0.7.0",
    author="Raghunandan Rao",
    author_email="r.raghunandan@gmail.com",
    url="https://github.com/rags/pynt",
    packages=["pynt"],
    entry_points =  {'console_scripts': ['pynt=pynt:main']}, 
    license="MIT License",
    description="Lightweight Python Build Tool.",
    long_description=open("README.rst").read()+"\n"+open("CHANGES.rst").read()
)
