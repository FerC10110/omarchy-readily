import QtQuick
import qs.Commons
import qs.Ui
import "ReadilyModel.js" as Model

// The list: section tabs, a search box that also filters by #tag, and the
// items. Choosing an item asks the panel to copy it; nothing here reads a file
// or touches the clipboard.
Item {
  id: view

  property var host: null
  property int selected: 0
  property var suggestions: []
  property int suggestion: 0

  readonly property Item focusItem: search
  readonly property color fg: host ? host.foreground : Color.foreground
  readonly property color dim: host ? host.dim : Qt.darker(Color.foreground, 1.55)
  readonly property color urgent: host ? host.urgent : Color.urgent
  readonly property string family: host ? host.fontFamily : Style.font.family
  readonly property var sections: host ? (host.payload.sections || []) : []
  readonly property string sectionKey: host ? host.section : Model.ALL
  readonly property var tabs: Model.sectionTabs(sections)
  readonly property var rows: Model.filterItems(sections, sectionKey, host ? host.query : "")
  readonly property string sectionError: {
    for (var i = 0; i < sections.length; i++)
      if (sections[i].name === sectionKey) return sections[i].error || ""
    return ""
  }

  implicitHeight: column.implicitHeight

  onRowsChanged: if (selected >= rows.length) selected = Math.max(0, rows.length - 1)

  // The panel clears the query each time it opens.
  Connections {
    target: view.host
    function onQueryChanged() {
      if (search.text !== view.host.query) search.text = view.host.query
    }
  }

  function selectSection(key) {
    host.section = key
    selected = 0
    search.forceActiveFocus()
  }

  function cycleSection(direction) {
    var index = 0
    for (var i = 0; i < tabs.length; i++)
      if (tabs[i].key === sectionKey) index = i
    selectSection(tabs[(index + direction + tabs.length) % tabs.length].key)
  }

  function moveSelection(delta) {
    if (rows.length === 0) return
    selected = Math.max(0, Math.min(rows.length - 1, selected + delta))
    list.positionViewAtIndex(selected, ListView.Contain)
  }

  function updateSuggestions() {
    var at = Model.wordAt(search.text, search.cursorPosition)
    if (!host || at.word.charAt(0) !== "#") {
      suggestions = []
      return
    }
    var others = Model.parseQuery(search.text.slice(0, at.start) + " " + search.text.slice(at.end)).tags
    suggestions = Model.suggestTags(host.payload.tags, at.word, others, 8)
    suggestion = 0
  }

  function acceptSuggestion(index) {
    var chosen = suggestions[index]
    if (!chosen) return
    var next = Model.completeTag(search.text, search.cursorPosition, chosen.name)
    search.text = next.text
    search.cursorPosition = next.cursor
    suggestions = []
  }

  function filterByTag(tag) {
    host.section = Model.ALL
    search.text = "#" + tag + " "
    search.cursorPosition = search.text.length
    selected = 0
    suggestions = []
    search.forceActiveFocus()
  }

  function handleKey(event) {
    var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
    var shift = (event.modifiers & Qt.ShiftModifier) !== 0
    if (suggestions.length > 0 && !ctrl) {
      if (event.key === Qt.Key_Down) {
        suggestion = Math.min(suggestion + 1, suggestions.length - 1)
        event.accepted = true
        return
      }
      if (event.key === Qt.Key_Up) {
        suggestion = Math.max(suggestion - 1, 0)
        event.accepted = true
        return
      }
      if (event.key === Qt.Key_Tab || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
        acceptSuggestion(suggestion)
        event.accepted = true
        return
      }
      if (event.key === Qt.Key_Escape) {
        suggestions = []
        event.accepted = true
        return
      }
    }
    if (ctrl && (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab)) {
      cycleSection(event.key === Qt.Key_Backtab || shift ? -1 : 1)
    } else if (ctrl && event.key === Qt.Key_S) {
      host.startSave()
    } else if (ctrl && event.key === Qt.Key_O) {
      host.openSection()
    } else if (event.key === Qt.Key_Down) {
      moveSelection(1)
    } else if (event.key === Qt.Key_Up) {
      moveSelection(-1)
    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      if (rows[selected]) host.copyItem(rows[selected])
    } else if (event.key === Qt.Key_Escape) {
      if (search.text !== "") search.text = ""
      else host.close()
    } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
      // Keep focus in the search box.
    } else {
      return
    }
    event.accepted = true
  }

  Column {
    id: column
    width: parent.width
    spacing: Style.space(8)

    Item {
      width: parent.width
      height: Math.max(heading.implicitHeight, actions.implicitHeight)

      Text {
        id: heading
        anchors.verticalCenter: parent.verticalCenter
        text: "Readily"
        textFormat: Text.PlainText
        color: view.fg
        font.family: view.family
        font.pixelSize: Style.font.title
        font.bold: true
      }

      Row {
        id: actions
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(6)

        Button {
          text: "Save"
          iconText: "󰆓"
          bordered: true
          tooltipText: "Save what is copied (Ctrl+S)"
          foreground: view.fg
          fontFamily: view.family
          onClicked: view.host.startSave()
        }

        Button {
          text: "Obsidian"
          iconText: "󰏌"
          bordered: true
          enabled: view.sectionKey !== Model.ALL
          opacity: enabled ? 1 : 0.55
          tooltipText: enabled ? "Open " + view.sectionKey + " (Ctrl+O)" : "Pick a section to open it"
          foreground: view.fg
          fontFamily: view.family
          onClicked: view.host.openSection()
        }
      }
    }

    Flickable {
      width: parent.width
      height: tabRow.implicitHeight
      contentWidth: tabRow.implicitWidth
      contentHeight: height
      clip: true
      flickableDirection: Flickable.HorizontalFlick
      boundsBehavior: Flickable.StopAtBounds
      interactive: contentWidth > width

      Row {
        id: tabRow
        spacing: Style.space(4)

        Repeater {
          model: view.tabs

          Button {
            required property var modelData
            text: modelData.label + (modelData.error ? " ⚠" : "")
            selected: view.sectionKey === modelData.key
            foreground: view.fg
            fontFamily: view.family
            fontSize: Style.font.bodySmall
            onClicked: view.selectSection(modelData.key)
          }
        }
      }
    }

    TextField {
      id: search
      width: parent.width
      placeholderText: "Search, or #tag"
      foreground: view.fg
      font.family: view.family
      onTextChanged: {
        if (view.host && view.host.query !== text) view.host.query = text
        view.selected = 0
        view.updateSuggestions()
      }
      onCursorPositionChanged: view.updateSuggestions()
      Keys.onPressed: function(event) { view.handleKey(event) }
    }

    Column {
      width: parent.width
      visible: view.suggestions.length > 0
      spacing: Style.space(2)

      Repeater {
        model: view.suggestions

        Rectangle {
          required property var modelData
          required property int index
          width: parent.width
          height: suggestionText.implicitHeight + Style.space(6)
          radius: Style.cornerRadius
          color: index === view.suggestion ? Style.selectionFillFor(view.fg, Color.accent) : "transparent"

          Text {
            id: suggestionText
            x: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            text: "#" + modelData.name + "   " + modelData.count
            textFormat: Text.PlainText
            color: view.fg
            font.family: view.family
            font.pixelSize: Style.font.bodySmall
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: view.acceptSuggestion(index)
          }
        }
      }
    }

    Text {
      width: parent.width
      visible: text !== ""
      text: view.host && view.host.notice !== "" ? view.host.notice : view.sectionError
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: view.host && view.host.notice !== "" && !view.host.noticeIsError ? view.dim : view.urgent
      font.family: view.family
      font.pixelSize: Style.font.bodySmall
    }

    ListView {
      id: list
      width: parent.width
      height: Math.min(contentHeight, Style.space(430))
      visible: view.rows.length > 0
      clip: true
      spacing: Style.space(2)
      boundsBehavior: Flickable.StopAtBounds
      model: view.rows

      delegate: ItemRow {
        required property var modelData
        required property int index
        width: list.width
        host: view.host
        entry: modelData
        selected: index === view.selected
        showSection: view.sectionKey === Model.ALL
        onActivated: view.host.copyItem(modelData)
        onTagClicked: function(tag) { view.filterByTag(tag) }
      }
    }

    Text {
      width: parent.width
      visible: view.rows.length === 0 && view.sectionError === ""
      text: view.host && view.host.query !== "" ? "No matches."
        : (view.sectionKey === Model.ALL ? "Nothing saved yet. Copy something and press Save."
          : "Nothing in " + view.sectionKey + " yet. Copy something and press Save.")
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: view.dim
      font.family: view.family
      font.pixelSize: Style.font.bodySmall
    }

    PanelSeparator {
      width: parent.width
      foreground: view.fg
    }

    Item {
      width: parent.width
      height: Math.max(folderText.implicitHeight, change.implicitHeight)

      Text {
        id: folderText
        width: parent.width - change.implicitWidth - Style.space(8)
        text: view.host ? Model.tildePath(view.host.payload.folder, view.host.home) : ""
        textFormat: Text.PlainText
        elide: Text.ElideMiddle
        color: view.dim
        font.family: view.family
        font.pixelSize: Style.font.caption
      }

      Text {
        id: change
        anchors.right: parent.right
        text: "Change"
        textFormat: Text.PlainText
        color: changeArea.containsMouse ? view.fg : view.dim
        font.family: view.family
        font.pixelSize: Style.font.caption
        font.underline: true

        MouseArea {
          id: changeArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: view.host.showSetup("")
        }
      }
    }
  }
}
