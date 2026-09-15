import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "ReadilyModel.js" as Model

// Save what is copied: a preview of the clipboard as the script read it, an
// optional title and tags, and the section to add it to. The panel runs the
// save; this view only collects the choices.
Item {
  id: view

  property var host: null
  property var tags: []
  property string sectionName: ""
  property bool creating: false
  property string tagError: ""
  property var suggestions: []
  property int suggestion: 0

  readonly property Item focusItem: titleField
  readonly property color fg: host ? host.foreground : Color.foreground
  readonly property color dim: host ? host.dim : Qt.darker(Color.foreground, 1.55)
  readonly property color urgent: host ? host.urgent : Color.urgent
  readonly property string family: host ? host.fontFamily : Style.font.family
  readonly property var peek: host ? host.peek : ({ state: "", message: "", preview: "", lineCount: 0, title: "", image: "", hash: "" })
  readonly property var sectionNames: host ? (host.payload.sections || []).map(function(s) { return s.name }) : []
  readonly property var allTags: host ? (host.payload.tags || []) : []
  readonly property bool clipUsable: (peek.state === "text" || peek.state === "image") && peek.hash !== ""
  readonly property var previewLines: peek.state === "text" ? String(peek.preview || "").split("\n") : []
  readonly property string newName: newSection.text.trim()
  // The name rules are for new sections; typing the name of one that exists uses it.
  readonly property string newNameError: {
    if (!creating || newSection.text === "" || sectionNames.indexOf(newName) !== -1) return ""
    if (!Model.validSectionName(newName)) return "Use letters, digits, spaces, - and _"
    var existing = Model.caseDuplicate(sectionNames, newName)
    return existing !== "" ? "A section named " + existing + " already exists" : ""
  }
  readonly property bool canSave: host !== null && clipUsable && !host.saving
    && (creating ? newName !== "" && newNameError === "" : sectionName !== "")

  implicitHeight: heading.implicitHeight + column.implicitHeight + footer.implicitHeight + 2 * Style.space(6)

  onCreatingChanged: {
    if (creating && visible) Qt.callLater(function() { newSection.forceActiveFocus() })
  }
  onSuggestionChanged: showSuggestion()
  onSuggestionsChanged: showSuggestion()
  onTagsChanged: if (tagField.activeFocus) ensureVisible(tagField)
  onTagErrorChanged: if (tagError !== "") ensureVisible(tagErrorText)
  onNewNameErrorChanged: if (newNameError !== "") ensureVisible(nameErrorText)

  function reset(initialTags, initialSection) {
    tags = (initialTags || []).slice()
    sectionName = initialSection || ""
    creating = sectionNames.length === 0
    titleField.text = ""
    tagField.text = ""
    newSection.text = ""
    tagError = ""
    suggestions = []
    form.contentY = 0
  }

  // The form scrolls when the card is too short for it; keep what the keyboard
  // is on in sight. Runs after the change that moved it has been laid out.
  function ensureVisible(item) {
    Qt.callLater(function() {
      if (!item || !item.visible) return
      column.forceLayout()
      var margin = Style.space(6)
      var top = item.mapToItem(column, 0, 0).y
      var bottom = top + item.height
      var maxY = Math.max(0, form.contentHeight - form.height)
      if (top < form.contentY + margin) form.contentY = Math.max(0, top - margin)
      else if (bottom > form.contentY + form.height - margin) form.contentY = Math.min(maxY, bottom + margin - form.height)
    })
  }

  function showSuggestion() {
    Qt.callLater(function() {
      if (suggestions.length === 0) return
      tagSuggestions.forceLayout()
      ensureVisible(tagSuggestions.itemAt(suggestion))
    })
  }

  function addTypedTag() {
    var raw = tagField.text.trim()
    if (raw === "") return true
    var tag = Model.normalizeTag(raw)
    if (tag === "") {
      tagError = "Not a valid tag"
      return false
    }
    if (tags.indexOf(tag) === -1) tags = tags.concat([tag])
    tagField.text = ""
    tagError = ""
    suggestions = []
    return true
  }

  function removeTag(tag) {
    tags = tags.filter(function(t) { return t !== tag })
  }

  function updateSuggestions() {
    var typed = tagField.text.trim()
    suggestions = typed === "" ? [] : Model.suggestTags(allTags, typed, tags, 8)
    suggestion = 0
  }

  function acceptSuggestion(index) {
    var chosen = suggestions[index]
    if (!chosen) return
    if (tags.indexOf(chosen.name) === -1) tags = tags.concat([chosen.name])
    tagField.text = ""
    tagError = ""
    suggestions = []
  }

  // Up and Down walk the sections and then "+ New section".
  function moveSection(delta) {
    var index = creating ? sectionNames.length : sectionNames.indexOf(sectionName)
    index = Math.max(0, Math.min(sectionNames.length, index + delta))
    if (index === sectionNames.length) {
      creating = true
    } else {
      creating = false
      sectionName = sectionNames[index]
    }
    sectionList.positionViewAtIndex(Math.min(index, sectionNames.length - 1), ListView.Contain)
    ensureVisible(creating ? newSection : sectionList.itemAtIndex(index))
  }

  function submit() {
    if (!addTypedTag() || !canSave) return
    host.submitSave(creating ? newName : sectionName, creating, titleField.text, tags)
  }

  function cycleFocus(direction) {
    var order = creating ? [titleField, tagField, newSection] : [titleField, tagField]
    var index = 0
    for (var i = 0; i < order.length; i++)
      if (order[i].activeFocus) index = i
    order[(index + direction + order.length) % order.length].forceActiveFocus()
  }

  function handleKey(event, field) {
    var enter = event.key === Qt.Key_Return || event.key === Qt.Key_Enter
    if (field === tagField) {
      if (suggestions.length > 0) {
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
        if (event.key === Qt.Key_Tab || enter) {
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
      if (event.text === " " || event.text === "," || (enter && tagField.text.trim() !== "")) {
        addTypedTag()
        event.accepted = true
        return
      }
      if (event.key === Qt.Key_Backspace && tagField.text === "" && tags.length > 0) {
        tags = tags.slice(0, tags.length - 1)
        event.accepted = true
        return
      }
    }
    if (enter) {
      submit()
    } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
      cycleFocus(event.key === Qt.Key_Backtab || (event.modifiers & Qt.ShiftModifier) ? -1 : 1)
    } else if (field !== newSection && event.key === Qt.Key_Down) {
      moveSection(1)
    } else if (field !== newSection && event.key === Qt.Key_Up) {
      moveSection(-1)
    } else if (event.key === Qt.Key_Escape) {
      host.backToList()
    } else {
      return
    }
    event.accepted = true
  }

  Text {
    id: heading
    text: "Save to Readily"
    textFormat: Text.PlainText
    color: view.fg
    font.family: view.family
    font.pixelSize: Style.font.title
    font.bold: true
  }

  // Everything whose height varies scrolls here, so the error line and the
  // buttons below always stay on the card.
  Flickable {
    id: form
    anchors.top: heading.bottom
    anchors.topMargin: Style.space(6)
    anchors.bottom: footer.top
    anchors.bottomMargin: Style.space(6)
    width: parent.width
    contentWidth: width
    contentHeight: column.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    interactive: contentHeight > height
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Column {
      id: column
      width: form.width
      spacing: Style.space(6)

      Rectangle {
        width: parent.width
        height: previewColumn.implicitHeight + Style.space(12)
        radius: Style.cornerRadius
        color: Qt.rgba(view.fg.r, view.fg.g, view.fg.b, 0.06)

        Column {
          id: previewColumn
          x: Style.space(8)
          y: Style.space(6)
          width: parent.width - Style.space(16)
          spacing: Style.space(2)

          Repeater {
            model: view.previewLines

            Text {
              required property var modelData
              width: parent.width
              text: modelData
              textFormat: Text.PlainText
              elide: Text.ElideRight
              color: view.fg
              font.family: view.family
              font.pixelSize: Style.font.bodySmall
            }
          }

          Text {
            visible: view.peek.state === "text" && view.peek.lineCount > view.previewLines.length
            text: "+" + (view.peek.lineCount - view.previewLines.length) + " lines"
            textFormat: Text.PlainText
            color: view.dim
            font.family: view.family
            font.pixelSize: Style.font.caption
          }

          Image {
            visible: view.peek.state === "image" && view.peek.image !== ""
            width: parent.width
            height: visible ? Style.space(160) : 0
            source: visible ? Model.fileUrl(view.peek.image) : ""
            sourceSize.height: Style.space(320)
            fillMode: Image.PreserveAspectFit
            horizontalAlignment: Image.AlignLeft
            asynchronous: true
          }

          Text {
            width: parent.width
            visible: !view.clipUsable
            text: view.peek.state === "" ? "Reading the clipboard…" : (view.peek.message || "Nothing to save")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: view.peek.state === "" ? view.dim : view.urgent
            font.family: view.family
            font.pixelSize: Style.font.bodySmall
          }
        }
      }

      Text {
        text: "Title"
        textFormat: Text.PlainText
        color: view.dim
        font.family: view.family
        font.pixelSize: Style.font.caption
      }

      TextField {
        id: titleField
        width: parent.width
        placeholderText: view.peek.state === "image" ? "Image " + Qt.formatDateTime(new Date(), "yyyy-MM-dd hh:mm")
          : (view.peek.title || "Optional")
        foreground: view.fg
        font.family: view.family
        onActiveFocusChanged: if (activeFocus) view.ensureVisible(titleField)
        Keys.onPressed: function(event) { view.handleKey(event, titleField) }
      }

      Text {
        text: "Tags"
        textFormat: Text.PlainText
        color: view.dim
        font.family: view.family
        font.pixelSize: Style.font.caption
      }

      Flow {
        width: parent.width
        visible: view.tags.length > 0
        spacing: Style.space(4)

        Repeater {
          model: view.tags

          Rectangle {
            required property var modelData
            width: chip.implicitWidth + Style.space(10)
            height: chip.implicitHeight + Style.space(4)
            radius: height / 2
            color: chipArea.containsMouse ? Style.hoverFillFor(view.fg, Color.accent)
              : Qt.rgba(view.fg.r, view.fg.g, view.fg.b, 0.1)

            Text {
              id: chip
              anchors.centerIn: parent
              text: "#" + modelData + "  ×"
              textFormat: Text.PlainText
              color: view.fg
              font.family: view.family
              font.pixelSize: Style.font.caption
            }

            MouseArea {
              id: chipArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: view.removeTag(modelData)
            }
          }
        }
      }

      TextField {
        id: tagField
        width: parent.width
        placeholderText: "Add a tag and press Enter"
        foreground: view.fg
        font.family: view.family
        onTextChanged: {
          view.tagError = ""
          view.updateSuggestions()
        }
        onActiveFocusChanged: if (activeFocus) view.ensureVisible(tagField)
        Keys.onPressed: function(event) { view.handleKey(event, tagField) }
      }

      TagSuggestions {
        id: tagSuggestions
        width: parent.width
        suggestions: view.suggestions
        current: view.suggestion
        foreground: view.fg
        fontFamily: view.family
        onPicked: function(index) { view.acceptSuggestion(index) }
      }

      Text {
        id: tagErrorText
        visible: view.tagError !== ""
        text: view.tagError
        textFormat: Text.PlainText
        color: view.urgent
        font.family: view.family
        font.pixelSize: Style.font.caption
      }

      Text {
        text: "Section"
        textFormat: Text.PlainText
        color: view.dim
        font.family: view.family
        font.pixelSize: Style.font.caption
      }

      ListView {
        id: sectionList
        width: parent.width
        height: Math.min(contentHeight, Style.space(150))
        visible: view.sectionNames.length > 0
        clip: true
        spacing: Style.space(2)
        boundsBehavior: Flickable.StopAtBounds
        model: view.sectionNames

        delegate: Button {
          required property var modelData
          width: sectionList.width
          leftAlign: true
          selected: !view.creating && view.sectionName === modelData
          text: modelData
          foreground: view.fg
          fontFamily: view.family
          onClicked: {
            view.creating = false
            view.sectionName = modelData
          }
        }
      }

      Button {
        width: parent.width
        leftAlign: true
        selected: view.creating
        text: "+ New section"
        foreground: view.fg
        fontFamily: view.family
        onClicked: view.creating = true
      }

      TextField {
        id: newSection
        width: parent.width
        visible: view.creating
        placeholderText: "Section name, e.g. commands"
        foreground: view.fg
        font.family: view.family
        onActiveFocusChanged: if (activeFocus) view.ensureVisible(newSection)
        Keys.onPressed: function(event) { view.handleKey(event, newSection) }
      }

      Text {
        id: nameErrorText
        visible: view.newNameError !== ""
        text: view.newNameError
        textFormat: Text.PlainText
        color: view.urgent
        font.family: view.family
        font.pixelSize: Style.font.caption
      }
    }
  }

  // The error line sits right above the buttons, pinned to the bottom of the card.
  Column {
    id: footer
    anchors.bottom: parent.bottom
    width: parent.width
    spacing: Style.space(6)

    Text {
      width: parent.width
      visible: text !== ""
      text: view.host ? view.host.notice : ""
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: view.urgent
      font.family: view.family
      font.pixelSize: Style.font.bodySmall
    }

    Item {
      width: parent.width
      height: buttons.implicitHeight

      Row {
        id: buttons
        anchors.right: parent.right
        spacing: Style.space(6)

        Button {
          text: "Cancel"
          bordered: true
          foreground: view.fg
          fontFamily: view.family
          onClicked: view.host.backToList()
        }

        Button {
          text: view.host && view.host.saving ? "Saving…" : "Save"
          iconText: "󰆓"
          bordered: true
          enabled: view.canSave
          opacity: enabled ? 1 : 0.55
          foreground: view.fg
          fontFamily: view.family
          onClicked: view.submit()
        }
      }
    }
  }
}
