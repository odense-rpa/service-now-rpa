"""Demo of the RPA process client (read-only demo)."""

from snow import Driftsstatus, RpaClient


def main():
    with RpaClient.from_env() as rpa:
        proc = rpa.get("BSN0002394")
        print(f"{proc.number}: {proc.name}")
        print(f"  driftsstatus: {proc.driftsstatus}")
        print(f"  forvaltning:  {proc.forvaltning}")
        print(f"  persondata:   {proc.persondata_i_processen}")

        print("\nPauserede processer:")
        for p in rpa.list(driftsstatus=Driftsstatus.PAUSE):
            print(f"  {p.number}  {p.name}")


if __name__ == "__main__":
    main()
