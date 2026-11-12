import enum


class DisplayManagerEnum(enum.Enum):
    LigthDM = enum.auto()
    SDDM    = enum.auto()
    GDM     = enum.auto()


def get_display_manager() -> DisplayManagerEnum:
    """ Get the display manager in use """
    try:
        with open("/etc/X11/default-display-manager", "r") as f:
            dm = f.read().strip()
            if "lightdm" in dm:
                return DisplayManagerEnum.LigthDM
            elif "sddm" in dm:
                return DisplayManagerEnum.SDDM
            elif "gdm" in dm:
                return DisplayManagerEnum.GDM
            else:
                raise ValueError(f"Unknown display manager: {dm}")
    except FileNotFoundError:
        raise FileNotFoundError("Display manager file not found.")


__ALL__ = ["DisplayManagerEnum", "get_display_manager"]

if __name__ == "__main__":
    dm = get_display_manager()
    print(f"Display Manager: {dm.name}")