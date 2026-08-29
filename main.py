from agent import run_agent


def main():

    print("=" * 50)
    print("Mini AEC Compliance Agent")
    print("=" * 50)

    print(
        "Type 'exit' to quit.\n"
    )

    while True:

        user_input = input("You: ").strip()

        if user_input.lower() == "exit":
            print("Goodbye!")
            break

        if not user_input:
            continue

        try:
            answer = run_agent(user_input)

            print()
            print("Agent:")
            print(answer)
            print()

        except Exception as error:

            print()
            print("An error occurred:")
            print(error)
            print()


if __name__ == "__main__":
    main()