from Screens.Screen import Screen
from Screens.ParentalControlSetup import ProtectedScreen
from Components.Sources.List import List
from Components.ActionMap import NumberActionMap
from Components.Sources.StaticText import StaticText
from Components.config import configfile
from Components.PluginComponent import plugins
from Components.config import config
from Components.NimManager import nimmanager
from Components.SystemInfo import SystemInfo
from boxbranding import getBoxType
from Tools.BoundFunction import boundFunction
from Tools.Directories import resolveFilename, SCOPE_SKIN, fileExists
from enigma import eTimer

import xml.etree.cElementTree

from Screens.Setup import Setup, getSetupTitle

mainmenu = _("Main menu")

# read the menu
file = open(resolveFilename(SCOPE_SKIN, 'menu.xml'), 'r')
mdom = xml.etree.cElementTree.parse(file)
file.close()


class MenuUpdater:
	def __init__(self):
		self.updatedMenuItems = {}

	def addMenuItem(self, id, pos, text, module, screen, weight):
		if not self.updatedMenuAvailable(id):
			self.updatedMenuItems[id] = []
		self.updatedMenuItems[id].append([text, pos, module, screen, weight])

	def delMenuItem(self, id, pos, text, module, screen, weight):
		self.updatedMenuItems[id].remove([text, pos, module, screen, weight])

	def updatedMenuAvailable(self, id):
		return id in self.updatedMenuItems

	def getUpdatedMenu(self, id):
		return self.updatedMenuItems[id]

menuupdater = MenuUpdater()


class MenuSummary(Screen):
	
	if getBoxType() in ('dm800se','dm800','dm800sev2','dm500hd','dm500hdv2','dm7020hd','dm7020hdv2','dm520','dm820','dm7080','dm8000'):
		pass
	else:
		def __init__(self, session, parent):
			Screen.__init__(self, session, parent=parent)
			self["MenuTitle"] = StaticText(parent.getTitle())
			self["MenuEntry"] = StaticText("")
			self.onShow.append(self.addWatcher)
			self.onHide.append(self.removeWatcher)

		def addWatcher(self):
			self.parent["menu"].onSelectionChanged.append(self.selectionChanged)
	 		self.selectionChanged()

		def removeWatcher(self):
			self.parent["menu"].onSelectionChanged.remove(self.selectionChanged)

		def selectionChanged(self):
			self["MenuEntry"].text = self.parent["menu"].getCurrent()[0]


class Menu(Screen, ProtectedScreen):
	ALLOW_SUSPEND = True

	def okbuttonClick(self):
		if self.number:
			self["menu"].setIndex(self.number - 1)
		self.resetNumberKey()
		selection = self["menu"].getCurrent()
		if selection is not None:
			selection[1]()

	def execText(self, text):
		exec text

	def runScreen(self, arg):
		# arg[0] is the module (as string)
		# arg[1] is Screen inside this module
		#        plus possible arguments, as
		#        string (as we want to reference
		#        stuff which is just imported)
		# FIXME. somehow
		if arg[0] != "":
			exec "from " + arg[0] + " import *"
		self.openDialog(*eval(arg[1]))

	def nothing(self): #dummy
		pass

	def openDialog(self, *dialog): # in every layer needed
		self.session.openWithCallback(self.menuClosed, *dialog)

	def openSetup(self, dialog):
		self.session.openWithCallback(self.menuClosed, Setup, dialog)

	def addMenu(self, destList, node):
		requires = node.get("requires")
		if requires:
			if requires[0] == '!':
				if SystemInfo.get(requires[1:], False):
					return
			elif not SystemInfo.get(requires, False):
				return
		MenuTitle = _(node.get("text", "??").encode("UTF-8"))
		entryID = node.get("entryID", "undefined")
		weight = node.get("weight", 50)
		x = node.get("flushConfigOnClose")
		if x:
			a = boundFunction(self.session.openWithCallback, self.menuClosedWithConfigFlush, Menu, node)
		else:
			a = boundFunction(self.session.openWithCallback, self.menuClosed, Menu, node)
		#TODO add check if !empty(node.childNodes)
		destList.append((MenuTitle, a, entryID, weight))

	def menuClosedWithConfigFlush(self, *res):
		configfile.save()
		self.menuClosed(*res)

	def menuClosed(self, *res):
		if res and res[0]:
			self.close(True)

	def addItem(self, destList, node):
		requires = node.get("requires")
		if requires:
			if requires[0] == '!':
				if SystemInfo.get(requires[1:], False):
					return
			elif not SystemInfo.get(requires, False):
				return
		conditional = node.get("conditional")
		if conditional and not eval(conditional):
			return
		item_text = node.get("text", "").encode("UTF-8")
		entryID = node.get("entryID", "undefined")
		weight = node.get("weight", 50)
		for x in node:
			if x.tag == 'screen':
				module = x.get("module")
				screen = x.get("screen")

				if screen is None:
					screen = module

				# print module, screen
				if module:
					module = "Screens." + module
				else:
					module = ""

				# check for arguments. they will be appended to the
				# openDialog call
				args = x.text or ""
				screen += ", " + args

				destList.append((_(item_text or "??"), boundFunction(self.runScreen, (module, screen)), entryID, weight))
				return
			elif x.tag == 'plugin':
				extensions = x.get("extensions")
				system = x.get("system")
				screen = x.get("screen")

				if extensions:
					module = extensions
				elif system:
					module = system

				if screen is None:
					screen = module

				if extensions:
					module = "Plugins.Extensions." + extensions + '.plugin'
				elif system:
					module = "Plugins.SystemPlugins." + system + '.plugin'
				else:
					module = ""

				# check for arguments. they will be appended to the
				# openDialog call
				args = x.text or ""
				screen += ", " + args

				destList.append((_(item_text or "??"), boundFunction(self.runScreen, (module, screen)), entryID, weight))
				return
			elif x.tag == 'code':
				destList.append((_(item_text or "??"), boundFunction(self.execText, x.text), entryID, weight))
				return
			elif x.tag == 'setup':
				id = x.get("id")
				if item_text == "":
					item_text = _(getSetupTitle(id))
				else:
					item_text = _(item_text)
				destList.append((item_text, boundFunction(self.openSetup, id), entryID, weight))
				return
		destList.append((item_text, self.nothing, entryID, weight))


	def __init__(self, session, parent):
		Screen.__init__(self, session)
		list = []

		menuID = None
		for x in parent: #walk through the actual nodelist
			if not x.tag:
				continue
			if x.tag == 'item':
				item_level = int(x.get("level", 0))
				if item_level <= config.usage.setup_level.index:
					self.addItem(list, x)
					count += 1
			elif x.tag == 'menu':
				self.addMenu(list, x)
				count += 1
			elif x.tag == "id":
				menuID = x.get("val")
				count = 0

			if menuID is not None:
				# menuupdater?
				if menuupdater.updatedMenuAvailable(menuID):
					for x in menuupdater.getUpdatedMenu(menuID):
						if x[1] == count:
							list.append((x[0], boundFunction(self.runScreen, (x[2], x[3] + ", ")), x[4]))
							count += 1

		if menuID is not None:
			# plugins
			bhorder = []
			if fileExists(resolveFilename(SCOPE_SKIN, 'menuorder.bh')):
				file = open(resolveFilename(SCOPE_SKIN, 'menuorder.bh'), 'r')
				for line in file.readlines():
					parts = line.strip().split()
					res = (parts[0], parts[1])
					bhorder.append(res)
					file.close()
					
			for l in plugins.getPluginsForMenu(menuID):
				# check if a plugin overrides an existing menu
				plugin_menuid = l[2]
				for x in list:
					if x[2] == plugin_menuid:
						list.remove(x)
						break
					weight = l[3]
					for y in bhorder:
						if y[0] == plugin_menuid:
							weight = y[1]
							
				if len(l) > 4 and l[4]:
					list.append((l[0], boundFunction(l[1], self.session, self.close), l[2], weight or 50))
				else:
					list.append((l[0], boundFunction(l[1], self.session), l[2], weight or 50))

		# for the skin: first try a menu_<menuID>, then Menu
		self.skinName = [ ]
		if menuID is not None:
			self.skinName.append("menu_" + menuID)
		self.skinName.append("Menu")
		self.menuID = menuID
		ProtectedScreen.__init__(self)

		# Sort by Weight
		if config.usage.sort_menus.value:
			list.sort()
		else:
			list.sort(key=lambda x: int(x[3]))

		if config.usage.menu_show_numbers.value:
			list = [(str(x[0] + 1) + "  " +x[1][0], x[1][1], x[1][2]) for x in enumerate(list)]

		self["menu"] = List(list)

		self["actions"] = NumberActionMap(["OkCancelActions", "MenuActions", "NumberActions"],
			{
				"ok": self.okbuttonClick,
				"cancel": self.closeNonRecursive,
				"menu": self.closeRecursive,
				"0": self.keyNumberGlobal,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal
			})

		a = parent.get("title", "").encode("UTF-8") or None
		a = a and _(a) or _(parent.get("text", "").encode("UTF-8"))
		self.setTitle(a)

		self.number = 0
		self.nextNumberTimer = eTimer()
		self.nextNumberTimer.callback.append(self.okbuttonClick)

	def keyNumberGlobal(self, number):
		self.number = self.number * 10 + number
		if self.number and self.number <= len(self["menu"].list):
			if number * 10 > len(self["menu"].list) or self.number >= 10:
				self.okbuttonClick()
			else:
				self.nextNumberTimer.start(1500, True)
		else:
			self.resetNumberKey()

	def resetNumberKey(self):
		self.nextNumberTimer.stop()
		self.number = 0

	def closeNonRecursive(self):
		self.resetNumberKey()
		self.close(False)

	def closeRecursive(self):
		self.resetNumberKey()
		self.close(True)

	def createSummary(self):
		return MenuSummary

	def isProtected(self):
		if config.ParentalControl.setuppinactive.value:
			if config.ParentalControl.config_sections.main_menu.value and not(hasattr(self.session, 'infobar') and self.session.infobar is None):
				return self.menuID == "mainmenu"
			elif config.ParentalControl.config_sections.configuration.value and self.menuID == "setup":
				return True
			elif config.ParentalControl.config_sections.standby_menu.value and self.menuID == "shutdown":
				return True
class MainMenu(Menu):
	#add file load functions for the xml-file

	def __init__(self, *x):
		self.skinName = "Menu"
		Menu.__init__(self, *x)
