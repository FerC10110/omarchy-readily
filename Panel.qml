import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "ReadilyModel.js" as Model

// The panel is a thin face over bin/readily: every file read, every write and
// every clipboard access happens in that script, and the panel only shows the
// JSON it prints. Three views share the card: choosing the folder, the list of
// items, and the form that saves what is copied. The card drops down from the
// bar icon when clicked, and opens in the middle of the screen when a keybinding
// calls it.
Panel {
  id: root
  moduleName: "io.github.ferc10110.readily"
  ipcTarget: "io.github.ferc10110.readily"
  // Its own IpcHandler below adds `save` to open/close/toggle.
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null

  property string view: "items"               // "setup" | "items" | "save"
  property var where: ({ folder: "", source: "none", exists: false, vault: "", error: "" })
  property var suggestions: []
  property var payload: ({ folder: "", tags: [], sections: [] })
  property var peek: emptyPeek()
  property string section: Model.ALL          // remembered while the shell runs
  property string query: ""
  property var lastTags: []                   // tags of the last save, while the shell runs
  property string notice: ""
  property bool noticeIsError: false
  property bool saveWhenReady: false
  property var pendingSave: null
  property bool centered: false               // opened by a keybinding, not the bar icon

  readonly property bool saving: saveCmd.running
  readonly property string home: Quickshell.env("HOME") || ""
  readonly property string program: pluginPath("bin/readily")
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property real currentHeight: view === "setup" ? folderView.implicitHeight
    : (view === "save" ? saveView.implicitHeight : itemsView.implicitHeight)
  readonly property Item currentFocus: view === "setup" ? folderView.focusItem
    : (view === "save" ? saveView.focusItem : itemsView.focusItem)

  // Absolute path of a file shipped inside this plugin, wherever it is installed.
  function pluginPath(relative) {
    var url = String(Qt.resolvedUrl(relative))
    return url.indexOf("file://") === 0 ? decodeURIComponent(url.substring(7)) : url
  }

  function emptyPeek() {
    return { state: "", message: "", preview: "", lineCount: 0, title: "", image: "", hash: "" }
  }

  function parseJson(out) {
    try {
      var data = JSON.parse(String(out || ""))
      return data && typeof data === "object" ? data : null
    } catch (e) {
      return null
    }
  }

  function lastLine(err) {
    var lines = String(err || "").trim().split("\n")
    return lines[lines.length - 1].replace(/^readily: /, "")
  }

  function setNotice(message, isError) {
    notice = message || ""
    noticeIsError = isError === true
  }

  function focusCurrent() {
    Qt.callLater(function() {
      if (root.currentFocus) root.currentFocus.forceActiveFocus()
    })
  }

  function refresh() {
    whereCmd.start(["where", "--json"])
  }

  function showSetup(message) {
    setNotice(message, message !== "")
    saveWhenReady = false
    view = "setup"
    vaultsCmd.start(["vaults", "--json"])
  }

  function chooseFolder(path) {
    var folder = String(path || "").trim()
    if (folder === "") return
    setNotice("", false)
    initCmd.start(["init", "--", folder])
  }

  function loadList() {
    listCmd.start(["list", "--json"])
  }

  function startSave() {
    if (view === "setup") return
    var fromQuery = Model.parseQuery(query).tags
    var sections = payload.sections || []
    var initialSection = section !== Model.ALL ? section : (sections.length > 0 ? sections[0].name : "")
    peek = emptyPeek()
    setNotice("", false)
    saveView.reset(fromQuery.length > 0 ? fromQuery : lastTags, initialSection)
    view = "save"
    peekCmd.start(["peek", "--json"])
  }

  function backToList() {
    setNotice("", false)
    view = "items"
  }

  function submitSave(sectionName, create, title, tags) {
    if (saveCmd.running || peek.hash === "") return
    var args = ["save", "--title=" + title, "--expect=" + peek.hash]
    for (var i = 0; i < tags.length; i++) args.push("--tag=" + tags[i])
    if (create) args.push("--create")
    args.push("--", sectionName)
    pendingSave = { section: sectionName, tags: tags.slice() }
    setNotice("", false)
    saveCmd.start(args)
  }

  function copyItem(row) {
    if (!row || copyCmd.running || row.item.missing === true) return
    copyCmd.start(["copy", "--", row.section, String(row.item.index), row.item.hash])
  }

  // Right-click or Ctrl+E on an entry: the section's note in the built-in editor.
  function editItem(row) {
    if (!row || row.item.missing === true) return
    noteEditor.openSection(row.section)
  }

  function openSection(name) {
    if (!name || name === Model.ALL || openCmd.running) return
    openCmd.start(["open", "--", name])
  }

  function openForSave() {
    if (opened) {
      if (view === "items") startSave()
      return
    }
    saveWhenReady = true
    openCentered()
  }

  function openCentered() {
    if (opened) return
    centered = true
    open()
  }

  onOpenedChanged: {
    if (opened) {
      setNotice("", false)
      query = ""
      view = "items"
      refresh()
      focusCurrent()
    } else {
      saveWhenReady = false
      centered = false
    }
  }

  onViewChanged: focusCurrent()

  IpcHandler {
    target: root.ipcTarget

    function open(): void { root.openCentered() }
    function close(): void { root.close() }
    function toggle(): void { root.opened ? root.close() : root.openCentered() }
    function save(): void { root.openForSave() }
  }

  ReadilyCommand {
    id: whereCmd
    program: root.program
    onFinished: function(code, out, err) {
      var data = root.parseJson(out)
      if (!data) {
        root.showSetup(root.lastLine(err) || "Could not run readily")
        return
      }
      root.where = data
      if (data.error !== "") root.showSetup(data.error)
      else if (data.folder === "" || !data.exists) root.showSetup("")
      else root.loadList()
    }
  }

  ReadilyCommand {
    id: vaultsCmd
    program: root.program
    onFinished: function(code, out, err) {
      var data = root.parseJson(out)
      root.suggestions = data && Array.isArray(data.suggestions) ? data.suggestions : []
      folderView.resetChoice()
    }
  }

  ReadilyCommand {
    id: initCmd
    program: root.program
    onFinished: function(code, out, err) {
      if (code === 0) root.refresh()
      else root.setNotice(root.lastLine(err) || "Could not use that folder", true)
    }
  }

  ReadilyCommand {
    id: listCmd
    program: root.program
    onFinished: function(code, out, err) {
      if (code === 4) {
        root.refresh()
        return
      }
      var data = root.parseJson(out)
      if (code !== 0 || !data) {
        root.setNotice(root.lastLine(err) || "Could not read the sections", true)
        return
      }
      root.payload = data
      var names = (data.sections || []).map(function(s) { return s.name })
      if (root.section !== Model.ALL && names.indexOf(root.section) === -1) root.section = Model.ALL
      if (root.view === "setup") root.view = "items"
      if (root.saveWhenReady) {
        root.saveWhenReady = false
        root.startSave()
      }
    }
  }

  ReadilyCommand {
    id: peekCmd
    program: root.program
    onFinished: function(code, out, err) {
      var data = root.parseJson(out)
      if (data) {
        root.peek = data
      } else {
        var failed = root.emptyPeek()
        failed.state = "invalid"
        failed.message = root.lastLine(err) || "Could not read the clipboard"
        root.peek = failed
      }
    }
  }

  ReadilyCommand {
    id: saveCmd
    program: root.program
    onFinished: function(code, out, err) {
      if (code === 0) {
        var saved = root.pendingSave || { section: "", tags: [] }
        root.lastTags = saved.tags
        Quickshell.execDetached(["notify-send", "Readily", "Saved to " + saved.section])
        root.close()
        return
      }
      root.setNotice(root.lastLine(err) || "Could not save", true)
      if (code === 3) peekCmd.start(["peek", "--json"])
    }
  }

  ReadilyCommand {
    id: copyCmd
    program: root.program
    onFinished: function(code, out, err) {
      if (code === 0) {
        root.close()
        return
      }
      root.setNotice(root.lastLine(err) || "Could not copy", true)
      if (code === 3) root.loadList()
    }
  }

  ReadilyCommand {
    id: openCmd
    program: root.program
    onFinished: function(code, out, err) {
      if (code === 0) root.close()
      else root.setNotice(root.lastLine(err) || "Could not open the section", true)
    }
  }

  // The views live in one place and move into whichever card is showing.
  Item {
    id: views
    parent: root.centered ? centerHolder : panelHolder
    anchors.fill: parent

    FolderView {
      id: folderView
      anchors.fill: parent
      visible: root.view === "setup"
      host: root
    }

    ItemsView {
      id: itemsView
      anchors.fill: parent
      visible: root.view === "items"
      host: root
    }

    SaveView {
      id: saveView
      anchors.fill: parent
      visible: root.view === "save"
      host: root
    }
  }

  // The floating editor for one section's note, over the whole screen.
  NoteEditor {
    id: noteEditor
    host: root
  }

  // Opened from the bar icon: the card drops down from it.
  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened && !root.centered
    focusTarget: root.currentFocus
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(root.currentHeight, Style.space(640))

    Item {
      id: panelHolder
      anchors.fill: parent
    }
  }

  // Opened by a keybinding: the same card in the middle of the focused screen,
  // over a dimmed background like Omarchy's clipboard and menu.
  PanelWindow {
    id: centerWindow
    visible: root.opened && root.centered
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "io.github.ferc10110.readily"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onVisibleChanged: if (visible) root.focusCurrent()

    Rectangle {
      anchors.fill: parent
      color: Color.menu.scrim
    }

    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.AllButtons
      onClicked: root.close()
    }

    BorderSurface {
      id: centerCard
      anchors.centerIn: parent
      width: Math.round(Math.min(Style.space(420), centerWindow.width - Style.gapsOut * 2))
      height: Math.round(Math.min(root.currentHeight + panel.verticalContentInset, Style.space(640),
                                  centerWindow.height - Style.gapsOut * 2))
      color: Color.popups.background
      borderSpec: panel.borderSpec
      padding: panel.padding
      radius: Style.cornerRadius

      // Clicks on the card stay on the card.
      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
      }

      Item {
        id: centerHolder
        anchors.fill: parent
        anchors.topMargin: centerCard.contentTopInset
        anchors.rightMargin: centerCard.contentRightInset
        anchors.bottomMargin: centerCard.contentBottomInset
        anchors.leftMargin: centerCard.contentLeftInset
      }
    }
  }
}
