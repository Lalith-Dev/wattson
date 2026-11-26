import sys


def main() -> None:
    from wattson.agent import Agent

    question = " ".join(sys.argv[1:]) or "When is the greenest time to use power in L1?"
    print(Agent().ask(question))
