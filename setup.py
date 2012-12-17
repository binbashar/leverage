from distutils.core import setup

setup(
    name="pynt",
    version="0.6.0",
    author="Raghunandan Rao",
    author_email="r.raghunandan@gmail.com",
    url="https://github.com/rags/pynt",
    packages=["pynt"],
    license="MIT License",
    description="Lightweight Python Build Tool.",
    long_description=open("README.rst").read()+"\n"+open("CHANGES.rst").read()
)
