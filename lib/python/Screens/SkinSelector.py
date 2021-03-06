import mmap
import re

from enigma import ePicLoad, getDesktop
from os import listdir
from os.path import dirname, exists, isdir, join as pathjoin

from skin import DEFAULT_SKIN, DEFAULT_DISPLAY_SKIN, EMERGENCY_NAME, EMERGENCY_SKIN, currentDisplaySkin, currentPrimarySkin, domScreens
from Components.ActionMap import HelpableNumberActionMap
from Components.config import config
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Screens.HelpMenu import HelpableScreen
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Standby import TryQuitMainloop, QUIT_RESTART
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN, SCOPE_LCDSKIN, SCOPE_SKIN


class SkinSelector(Screen, HelpableScreen):
	skinTemplate = """
	<screen name="SkinSelector" position="center,center" size="%d,%d">
		<widget name="preview" position="center,%d" size="%d,%d" alphatest="blend" />
		<widget source="skins" render="Listbox" position="center,%d" size="%d,%d" enableWrapAround="1" scrollbarMode="showOnDemand">
			<convert type="TemplatedMultiContent">
				{
				"template": [
					MultiContentEntryText(pos = (%d, 0), size = (%d, %d), font = 0, flags = RT_HALIGN_LEFT | RT_VALIGN_CENTER, text = 1),
					MultiContentEntryText(pos = (%d, 0), size = (%d, %d), font = 0, flags = RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text = 2)
				],
				"fonts": [gFont("Regular",%d)],
				"itemHeight": %d
				}
			</convert>
		</widget>
		<widget source="description" render="Label" position="center,e-%d" size="%d,%d" font="Regular;%d" valign="center" />
		<widget source="key_red" render="Label" position="%d,e-%d" size="%d,%d" backgroundColor="key_red" font="Regular;%d" foregroundColor="key_text" halign="center" valign="center" />
		<widget source="key_green" render="Label" position="%d,e-%d" size="%d,%d" backgroundColor="key_green" font="Regular;%d" foregroundColor="key_text" halign="center" valign="center" />
	</screen>"""
	scaleData = [
		670, 570,
		10, 356, 200,
		230, 650, 240,
		10, 350, 30,
		370, 260, 30,
		25,
		30,
		85, 650, 25, 20,
		10, 50, 140, 40, 20,
		160, 50, 140, 40, 20
	]
	skin = None

	def __init__(self, session, screenTitle=_("GUI Skin")):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		if SkinSelector.skin is None:
			self.initialiseSkin()
		self.setTitle(screenTitle)
		self.rootDir = resolveFilename(SCOPE_SKIN)
		self.config = config.skin.primary_skin
		self.current = currentPrimarySkin
		self.xmlList = ["skin.xml"]
		self.onChangedEntry = []
		self["skins"] = List(enableWrapAround=True)
		self["preview"] = Pixmap()
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["description"] = StaticText(_("Please wait... Loading list..."))
		self["actions"] = HelpableNumberActionMap(self, ["SetupActions", "DirectionActions", "ColorActions"], {
			"ok": (self.save, _("Save and activate the currently selected skin")),
			"cancel": (self.cancel, _("Cancel any changes to the currently active skin")),
			"close": (self.cancelRecursive, _("Cancel any changes to the currently active skin and exit all menus")),
			"red": (self.cancel, _("Cancel any changes to the currently active skin")),
			"green": (self.save, _("Save and activate the currently selected skin")),
			"up": (self.up, _("Move to the previous skin")),
			"down": (self.down, _("Move to the next skin")),
			"left": (self.left, _("Move to the previous page")),
			"right": (self.right, _("Move to the next page"))
		}, -1, description=_("Skin Selection Actions"))
		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.showPic)
		self.onLayoutFinish.append(self.layoutFinished)

	def initialiseSkin(self):
		element, path = domScreens.get("SkinSelector", (None, None))
		if element is None:  # This skin does not have a SkinConverter screen.
			buildSkin = True
		else:  # Test the skin's SkinConverter screen to ensure it works with the new code.
			buildSkin = False
			widgets = element.findall("widget")
			if widgets is not None:
				for widget in widgets:
					name = widget.get("name", None)
					source = widget.get("source", None)
					if name and name in ("Preview", "SkinList") or source == "introduction":
						print("[SkinSelector] Warning: Current skin '%s' does not support this version of SkinSelector!    Please contact the skin's author!" % config.skin.primary_skin.value)
						del domScreens["SkinSelector"]  # It is incompatible, delete the screen from the skin.
						buildSkin = True
						break
		if buildSkin:  # Build the embedded skin and scale it to the current screen resolution.
			# The skin template is designed for a HD screen so the scaling factor is 720.
			SkinSelector.skin = SkinSelector.skinTemplate % tuple([x * getDesktop(0).size().height() / 720 for x in SkinSelector.scaleData])
			# print("[SkinSelector] DEBUG: Height=%d\n%s" % (getDesktop(0).size().height(), SkinSelector.skin))
		else:
			SkinSelector.skin = "<screen />"

	def showPic(self, picInfo=""):
		ptr = self.picload.getData()
		if ptr is not None:
			self["preview"].instance.setPixmap(ptr.__deref__())

	def layoutFinished(self):
		self.picload.setPara((self["preview"].instance.size().width(), self["preview"].instance.size().height(), 1.0, 1, 1, 1, "#ff000000"))
		self.refreshList()

	def refreshList(self):
		resolutions = {
			"480": _("NTSC"),
			"576": _("PAL"),
			"720": _("HD"),
			"1080": _("FHD"),
			"2160": _("4K"),
			"4320": _("8K"),
			"8640": _("16K")
		}
		emergency = _("<Emergency>")
		default = _("<Default>")
		defaultPicon = _("<Default+Picon>")
		current = _("<Current>")
		pending = _("<Pending restart>")
		displayPicon = pathjoin(dirname(DEFAULT_DISPLAY_SKIN), "skin_display_picon.xml")
		skinList = []
		# Find and list the available skins...
		for dir in [dir for dir in listdir(self.rootDir) if isdir(pathjoin(self.rootDir, dir))]:
			previewPath = pathjoin(self.rootDir, dir)
			for skinFile in self.xmlList:
				skin = pathjoin(dir, skinFile)
				skinPath = pathjoin(self.rootDir, skin)
				if exists(skinPath):
					skinSize = None
					resolution = None
					if skinFile == "skin.xml":
						with open(skinPath, "r") as fd:
							mm = mmap.mmap(fd.fileno(), 0, prot=mmap.PROT_READ)
							skinWidth = re.search("\<?resolution.*?\sxres\s*=\s*\"(\d+)\"", mm)
							skinHeight = re.search("\<?resolution.*?\syres\s*=\s*\"(\d+)\"", mm)
							if skinWidth and skinHeight:
								skinSize = "%sx%s" % (skinWidth.group(1), skinHeight.group(1))
							resolution = skinHeight and resolutions.get(skinHeight.group(1), None)
							mm.close()
						print("[SkinSelector] Resolution of skin '%s': '%s' (%s)." % (skinPath, "Unknown" if resolution is None else resolution, skinSize))
						# Code can be added here to reject unsupported resolutions.
					# The "piconprev.png" image should be "prevpicon.png" to keep it with its partner preview image.
					preview = pathjoin(previewPath, "piconprev.png" if skinFile == "skin_display_picon.xml" else "prev.png")
					if skin == EMERGENCY_SKIN:
						skinEntry = [EMERGENCY_NAME, emergency, dir, skin, resolution, skinSize, preview]
					elif skin == DEFAULT_SKIN:
						skinEntry = [dir, default, dir, skin, resolution, skinSize, preview]
					elif skin == DEFAULT_DISPLAY_SKIN:
						skinEntry = [default, default, dir, skin, resolution, skinSize, preview]
					elif skin == displayPicon:
						skinEntry = [dir, defaultPicon, dir, skin, resolution, skinSize, preview]
					else:
						skinEntry = [dir, "", dir, skin, resolution, skinSize, preview]
					if skin == self.current:
						skinEntry[1] = current
					elif skin == self.config.value:
						skinEntry[1] = pending
					skinEntry.append("%s  %s" % (skinEntry[0], skinEntry[1]))
					# 0=SortKey, 1=Label, 2=Flag, 3=Directory, 4=Skin, 5=Resolution, 6=SkinSize, 7=Preview, 8=Label + Flag
					skinList.append(tuple([skinEntry[0].upper()] + skinEntry))
		skinList.sort()
		self["skins"].setList(skinList)
		# Set the list pointer to the current skin...
		for index in range(len(skinList)):
			if skinList[index][4] == self.config.value:
				self["skins"].setIndex(index)
				break
		self.loadPreview()

	def loadPreview(self):
		self.changedEntry()
		current = self["skins"].getCurrent()
		preview = current[7]
		if not exists(preview):
			preview = resolveFilename(SCOPE_CURRENT_SKIN, "noprev.png")
		self.picload.startDecode(preview)
		resolution = current[5]
		msg = "" if resolution is None else " %s" % resolution
		if current[4] == self.config.value:
			self["description"].setText(_("Press OK to keep the currently selected%s skin.") % msg)
		else:
			self["description"].setText(_("Press OK to activate the selected%s skin.") % msg)

	def cancel(self):
		self.close(False)

	def cancelRecursive(self):
		self.close(True)

	def save(self):
		current = self["skins"].getCurrent()
		label = current[1]
		skin = current[4]
		if skin == self.config.value:
			if skin == self.current:
				print("[SkinSelector] Selected skin: '%s' (Unchanged!)" % pathjoin(self.rootDir, skin))
				self.cancel()
			else:
				print("[SkinSelector] Selected skin: '%s' (Trying to restart again!)" % pathjoin(self.rootDir, skin))
				restartBox = self.session.openWithCallback(self.restartGUI, MessageBox, _("To apply the selected '%s' skin the GUI needs to restart. Would you like to restart the GUI now?") % label, MessageBox.TYPE_YESNO)
				restartBox.setTitle(_("SkinSelector: Restart GUI"))
		elif skin == self.current:
			print("[SkinSelector] Selected skin: '%s' (Pending skin '%s' cancelled!)" % (pathjoin(self.rootDir, skin), pathjoin(self.rootDir, self.config.value)))
			self.config.value = skin
			self.config.save()
			self.cancel()
		else:
			print("[SkinSelector] Selected skin: '%s'" % pathjoin(self.rootDir, skin))
			restartBox = self.session.openWithCallback(self.restartGUI, MessageBox, _("To save and apply the selected '%s' skin the GUI needs to restart. Would you like to save the selection and restart the GUI now?") % label, MessageBox.TYPE_YESNO)
			restartBox.setTitle(_("SkinSelector: Restart GUI"))

	def restartGUI(self, answer):
		if answer is True:
			self.config.value = self["skins"].getCurrent()[4]
			self.config.save()
			self.session.open(TryQuitMainloop, QUIT_RESTART)
		self.refreshList()

	def up(self):
		self["skins"].up()
		self.loadPreview()

	def down(self):
		self["skins"].down()
		self.loadPreview()

	def left(self):
		self["skins"].pageUp()
		self.loadPreview()

	def right(self):
		self["skins"].pageDown()
		self.loadPreview()

	# For summary screen.
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def createSummary(self):
		return SkinSelectorSummary

	def getCurrentName(self):
		current = self["skins"].getCurrent()[1]
		if current:
			current = current.replace("_", " ")
		return current


class LcdSkinSelector(SkinSelector):
	def __init__(self, session, screenTitle=_("Display Skin")):
		SkinSelector.__init__(self, session, screenTitle=screenTitle)
		self.skinName = ["LcdSkinSelector", "SkinSelector"]
		self.rootDir = resolveFilename(SCOPE_LCDSKIN)
		self.config = config.skin.display_skin
		self.current = currentDisplaySkin
		self.xmlList = ["skin_display.xml", "skin_display_picon.xml"]


class SkinSelectorSummary(Screen):
	def __init__(self, session, parent):
		Screen.__init__(self, session, parent=parent)
		self["Name"] = StaticText("")
		if hasattr(self.parent, "onChangedEntry"):
			self.onShow.append(self.addWatcher)
			self.onHide.append(self.removeWatcher)

	def addWatcher(self):
		if hasattr(self.parent, "onChangedEntry"):
			self.parent.onChangedEntry.append(self.selectionChanged)
			self.selectionChanged()

	def removeWatcher(self):
		if hasattr(self.parent, "onChangedEntry"):
			self.parent.onChangedEntry.remove(self.selectionChanged)

	def selectionChanged(self):
		self["Name"].text = self.parent.getCurrentName()
