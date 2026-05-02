#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Run a command via ssh proxy server")
    parser.add_argument(
        "--proxy-name", required=True, help="The name of the proxy image to use"
    )


if __name__ == "__main__":
    main()
