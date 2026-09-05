"""Generate the small, deterministic IFC model committed for demos and tests."""

from pathlib import Path

from ifcopenshell.api.aggregate.assign_object import assign_object
from ifcopenshell.api.project.create_file import create_file
from ifcopenshell.api.pset.add_pset import add_pset
from ifcopenshell.api.pset.edit_pset import edit_pset
from ifcopenshell.api.root.create_entity import create_entity
from ifcopenshell.api.spatial.assign_container import assign_container
from ifcopenshell.api.unit.assign_unit import assign_unit

OUTPUT_FILE = Path(__file__).resolve().parents[1] / "examples" / "sample_office.ifc"


def build_sample() -> None:
    model = create_file("IFC4")
    project = create_entity(model, ifc_class="IfcProject", name="Sample Office")
    assign_unit(model)

    site = create_entity(model, ifc_class="IfcSite", name="Demo Site")
    building = create_entity(model, ifc_class="IfcBuilding", name="Office Building")
    storey = create_entity(model, ifc_class="IfcBuildingStorey", name="Level 1")
    assign_object(model, products=[site], relating_object=project)
    assign_object(model, products=[building], relating_object=site)
    assign_object(model, products=[storey], relating_object=building)

    door_specs = [
        ("Door-01", 780.0, "Lobby door", False),
        ("Door-02", 1000.0, "Main exit", True),
        ("Door-03", 920.0, "Office door", False),
    ]
    for name, width, description, is_external in door_specs:
        door = create_entity(model, ifc_class="IfcDoor", name=name)
        door.Description = description
        door.OverallWidth = width
        door.OverallHeight = 2100.0
        assign_container(model, products=[door], relating_structure=storey)
        pset = add_pset(model, product=door, name="Pset_DoorCommon")
        edit_pset(
            model,
            pset=pset,
            properties={"IsExternal": is_external, "FireRating": "FD30"},
        )
        accessibility_pset = add_pset(model, product=door, name="Pset_MiniAEC")
        edit_pset(
            model,
            pset=accessibility_pset,
            properties={
                "ClearOpeningWidth": model.createIfcLengthMeasure(width),
                "OnAccessibleRoute": True,
            },
        )

    model.write(str(OUTPUT_FILE))
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    build_sample()
