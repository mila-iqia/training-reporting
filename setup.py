#!/usr/bin/env python

from setuptools import setup


if __name__ == '__main__':
    setup(
        name='report',
        version='0.0.0',
        description='Analyse benchmark results',
        author='Pierre Delaunay',
        packages=[
            'report',
        ],
        entry_points={
            'console_scripts': [
                'mlbench-report = report.report:main',
            ]
        },
        include_package_data=True
    )
