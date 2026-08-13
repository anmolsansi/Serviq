def main() -> int:
    """Run the scaffold worker process.

    Durable consumers and jobs are attached by later tickets. The scaffold exits
    successfully so startup/import behavior can be validated without external systems.
    """
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
