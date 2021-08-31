"""Load a layout in Blender."""

from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import bpy

from avalon import api
from avalon.blender.pipeline import AVALON_CONTAINERS
from avalon.blender.pipeline import AVALON_CONTAINER_ID
from avalon.blender.pipeline import AVALON_PROPERTY
from openpype.hosts.blender.api import plugin


class BlendLayoutLoader(plugin.AssetLoader):
    """Load layout from a .blend file."""

    families = ["layout"]
    representations = ["blend"]

    label = "Link Layout"
    icon = "code-fork"
    color = "orange"

    def _remove(self, asset_group):
        objects = list(asset_group.children)

        for obj in objects:
            if obj.type == 'MESH':
                for material_slot in list(obj.material_slots):
                    if material_slot.material:
                        bpy.data.materials.remove(material_slot.material)
                bpy.data.meshes.remove(obj.data)
            elif obj.type == 'ARMATURE':
                objects.extend(obj.children)
                bpy.data.armatures.remove(obj.data)
            elif obj.type == 'CURVE':
                bpy.data.curves.remove(obj.data)
            elif obj.type == 'EMPTY':
                objects.extend(obj.children)
                bpy.data.objects.remove(obj)

    def _remove_asset_and_library(self, asset_group):
        libpath = asset_group.get(AVALON_PROPERTY).get('libpath')

        # Check how many assets use the same library
        count = 0
        for obj in bpy.data.collections.get(AVALON_CONTAINERS).all_objects:
            if obj.get(AVALON_PROPERTY).get('libpath') == libpath:
                count += 1

        self._remove(asset_group)

        bpy.data.objects.remove(asset_group)

        # If it is the last object to use that library, remove it
        if count == 1:
            library = bpy.data.libraries.get(bpy.path.basename(libpath))
            bpy.data.libraries.remove(library)

    def _process(self, libpath, asset_group, group_name, actions):
        with bpy.data.libraries.load(
            libpath, link=True, relative=False
        ) as (data_from, data_to):
            data_to.objects = data_from.objects

        parent = bpy.context.scene.collection

        empties = [obj for obj in data_to.objects if obj.type == 'EMPTY']

        container = None

        for empty in empties:
            if empty.get(AVALON_PROPERTY):
                container = empty
                break

        assert container, "No asset group found"

        # Children must be linked before parents,
        # otherwise the hierarchy will break
        objects = []
        nodes = list(container.children)

        for obj in nodes:
            obj.parent = asset_group

        for obj in nodes:
            objects.append(obj)
            nodes.extend(list(obj.children))

        objects.reverse()

        constraints = []

        armatures = [obj for obj in objects if obj.type == 'ARMATURE']

        for armature in armatures:
            for bone in armature.pose.bones:
                for constraint in bone.constraints:
                    if hasattr(constraint, 'target'):
                        constraints.append(constraint)

        for obj in objects:
            parent.objects.link(obj)

        for obj in objects:
            local_obj = plugin.prepare_data(obj, group_name)

            action = None

            if actions:
                action = actions.get(local_obj.name, None)

            if local_obj.type == 'MESH':
                plugin.prepare_data(local_obj.data, group_name)

                if obj != local_obj:
                    for constraint in constraints:
                        if constraint.target == obj:
                            constraint.target = local_obj

                for material_slot in local_obj.material_slots:
                    if material_slot.material:
                        plugin.prepare_data(material_slot.material, group_name)
            elif local_obj.type == 'ARMATURE':
                plugin.prepare_data(local_obj.data, group_name)

                if action is not None:
                    local_obj.animation_data.action = action
                elif local_obj.animation_data.action is not None:
                    plugin.prepare_data(
                        local_obj.animation_data.action, group_name)

                # Set link the drivers to the local object
                if local_obj.data.animation_data:
                    for d in local_obj.data.animation_data.drivers:
                        for v in d.driver.variables:
                            for t in v.targets:
                                t.id = local_obj

            if not local_obj.get(AVALON_PROPERTY):
                local_obj[AVALON_PROPERTY] = dict()

            avalon_info = local_obj[AVALON_PROPERTY]
            avalon_info.update({"container_name": group_name})

        objects.reverse()

        bpy.data.orphans_purge(do_local_ids=False)

        bpy.ops.object.select_all(action='DESELECT')

        return objects

    def process_asset(
        self, context: dict, name: str, namespace: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> Optional[List]:
        """
        Arguments:
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            context: Full parenthood of representation to load
            options: Additional settings dictionary
        """
        libpath = self.fname
        asset = context["asset"]["name"]
        subset = context["subset"]["name"]

        asset_name = plugin.asset_name(asset, subset)
        unique_number = plugin.get_unique_number(asset, subset)
        group_name = plugin.asset_name(asset, subset, unique_number)
        namespace = namespace or f"{asset}_{unique_number}"

        avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
        if not avalon_container:
            avalon_container = bpy.data.collections.new(name=AVALON_CONTAINERS)
            bpy.context.scene.collection.children.link(avalon_container)

        asset_group = bpy.data.objects.new(group_name, object_data=None)
        asset_group.empty_display_type = 'SINGLE_ARROW'
        avalon_container.objects.link(asset_group)

        objects = self._process(libpath, asset_group, group_name, None)

        for child in asset_group.children:
            if child.get(AVALON_PROPERTY):
                avalon_container.objects.link(child)

        bpy.context.scene.collection.objects.link(asset_group)

        asset_group[AVALON_PROPERTY] = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": str(context["representation"]["_id"]),
            "libpath": libpath,
            "asset_name": asset_name,
            "parent": str(context["representation"]["parent"]),
            "family": context["representation"]["context"]["family"],
            "objectName": group_name
        }

        self[:] = objects
        return objects

    def update(self, container: Dict, representation: Dict):
        """Update the loaded asset.

        This will remove all objects of the current collection, load the new
        ones and add them to the collection.
        If the objects of the collection are used in another collection they
        will not be removed, only unlinked. Normally this should not be the
        case though.

        Warning:
            No nested collections are supported at the moment!
        """
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)
        libpath = Path(api.get_representation_path(representation))
        extension = libpath.suffix.lower()

        self.log.info(
            "Container: %s\nRepresentation: %s",
            pformat(container, indent=2),
            pformat(representation, indent=2),
        )

        assert asset_group, (
            f"The asset is not loaded: {container['objectName']}"
        )
        assert libpath, (
            "No existing library file found for {container['objectName']}"
        )
        assert libpath.is_file(), (
            f"The file doesn't exist: {libpath}"
        )
        assert extension in plugin.VALID_EXTENSIONS, (
            f"Unsupported file: {libpath}"
        )

        metadata = asset_group.get(AVALON_PROPERTY)
        group_libpath = metadata["libpath"]

        normalized_group_libpath = (
            str(Path(bpy.path.abspath(group_libpath)).resolve())
        )
        normalized_libpath = (
            str(Path(bpy.path.abspath(str(libpath))).resolve())
        )
        self.log.debug(
            "normalized_group_libpath:\n  %s\nnormalized_libpath:\n  %s",
            normalized_group_libpath,
            normalized_libpath,
        )
        if normalized_group_libpath == normalized_libpath:
            self.log.info("Library already loaded, not updating...")
            return

        actions = {}

        for obj in asset_group.children:
            obj_meta = obj.get(AVALON_PROPERTY)
            if obj_meta.get('family') == 'rig':
                rig = None
                for child in obj.children:
                    if child.type == 'ARMATURE':
                        rig = child
                        break
                if not rig:
                    raise Exception("No armature in the rig asset group.")
                if rig.animation_data and rig.animation_data.action:
                    instance_name = obj_meta.get('instance_name')
                    actions[instance_name] = rig.animation_data.action

        mat = asset_group.matrix_basis.copy()

        # Remove the children of the asset_group first
        for child in list(asset_group.children):
            self._remove_asset_and_library(child)

        # Check how many assets use the same library
        count = 0
        for obj in bpy.data.collections.get(AVALON_CONTAINERS).objects:
            if obj.get(AVALON_PROPERTY).get('libpath') == group_libpath:
                count += 1

        self._remove(asset_group)

        # If it is the last object to use that library, remove it
        if count == 1:
            library = bpy.data.libraries.get(bpy.path.basename(group_libpath))
            bpy.data.libraries.remove(library)

        self._process(str(libpath), asset_group, object_name, actions)

        avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
        for child in asset_group.children:
            if child.get(AVALON_PROPERTY):
                avalon_container.objects.link(child)

        asset_group.matrix_basis = mat

        metadata["libpath"] = str(libpath)
        metadata["representation"] = str(representation["_id"])

    def exec_remove(self, container: Dict) -> bool:
        """Remove an existing container from a Blender scene.

        Arguments:
            container (openpype:container-1.0): Container to remove,
                from `host.ls()`.

        Returns:
            bool: Whether the container was deleted.

        Warning:
            No nested collections are supported at the moment!
        """
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)

        if not asset_group:
            return False

        # Remove the children of the asset_group first
        for child in list(asset_group.children):
            self._remove_asset_and_library(child)

        self._remove_asset_and_library(asset_group)

        return True