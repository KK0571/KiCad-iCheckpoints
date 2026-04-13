import sys
import re
import os
import json

def patch_html(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"\nPatching: {input_file} -> {output_file}")

    # =========================================================================
    # Step 1: Inject "故障点" and "故障现象" into config.fields if missing
    # =========================================================================
    print("\n[Step 1] Injecting fields into config...")
    config_match = re.search(r'var\s+config\s*=\s*(\{.*?\});?', content)
    if config_match:
        try:
            config_json = config_match.group(1)
            fields_match = re.search(r'"fields":\s*(\[.*?\])', config_json)
            if fields_match:
                fields_str = fields_match.group(1)
                fields = json.loads(fields_str)
                added = False
                for field in ["故障点", "故障现象"]:
                    if field not in fields:
                        fields.append(field)
                        added = True
                if added:
                    new_fields_str = json.dumps(fields, ensure_ascii=False)
                    new_config_json = config_json.replace(fields_str, new_fields_str)
                    content = content.replace(config_json, new_config_json)
                    print("  [OK] Added missing fields to config.fields")
                else:
                    print("  [OK] Fields already present in config.fields")
            else:
                print("  [WARN] 'fields' key not found in config object")
        except Exception as e:
            print(f"  [WARN] Failed to update config fields: {e}")
    else:
        print("  [WARN] 'var config = ...' not found in file")

    # =========================================================================
    # Step 2: Inject CSS for editable cells
    # Use rfind to locate the LAST </style> (the main iBOM style block)
    # and insert our CSS just before it.
    # =========================================================================
    print("\n[Step 2] Injecting CSS...")
    css_block = """
    .editable-cell {
      cursor: pointer;
      background-color: rgba(255, 255, 0, 0.05);
    }
    .editable-cell:hover {
      background-color: rgba(255, 255, 0, 0.15);\
    }
    .cell-edit-input {
      width: 100%;
      box-sizing: border-box;
      padding: 2px;
      font-family: inherit;
      font-size: inherit;
      border: 1px solid #ccc;
      background-color: #fff;
      color: #000;
    }
"""
    style_close = '</style>'
    idx = content.rfind(style_close)
    if idx != -1:
        content = content[:idx] + css_block + content[idx:]
        print("  [OK] CSS injected before last </style>")
    else:
        print("  [WARN] </style> not found - CSS NOT injected")

    # =========================================================================
    # Step 3: Inject JS persistence functions
    # Injected just before 'function populateBomHeader' (stable anchor point).
    # Functions: saveCustomFields, initMissingFields, loadCustomFields,
    #            clearRepairInfo
    # =========================================================================
    print("\n[Step 3] Injecting JS persistence functions...")
    js_persistence = """
    function saveCustomFields() {
      var boardId = pcbdata.metadata.title + "_" + pcbdata.metadata.date;
      var key = "ibom_custom_fields_" + boardId;
      if (storage) {
        storage.setItem(storagePrefix + key, JSON.stringify(pcbdata.bom.fields));
      }
    }

    function initMissingFields() {
      // pcbdata.bom.fields is an object keyed by numeric IDs: {0: [...], 1: [...], ...}
      // Ensure every row has a slot for each field in config.fields, defaulting to ""
      var expectedLen = config.fields.length;
      for (var id in pcbdata.bom.fields) {
        var row = pcbdata.bom.fields[id];
        while (row.length < expectedLen) {
          row.push("");
        }
      }
    }

    function loadCustomFields() {
      initMissingFields();
      var boardId = pcbdata.metadata.title + "_" + pcbdata.metadata.date;
      var key = "ibom_custom_fields_" + boardId;
      var data = null;
      if (storage) {
        data = storage.getItem(storagePrefix + key);
      }
      if (data) {
        try {
          var savedFields = JSON.parse(data);
          var fpIdx  = config.fields.indexOf("故障点");
          var fphIdx = config.fields.indexOf("故障现象");
          for (var id in savedFields) {
            if (savedFields[id] && pcbdata.bom.fields[id]) {
              if (fpIdx  !== -1 && savedFields[id][fpIdx]  !== undefined)
                pcbdata.bom.fields[id][fpIdx]  = savedFields[id][fpIdx];
              if (fphIdx !== -1 && savedFields[id][fphIdx] !== undefined)
                pcbdata.bom.fields[id][fphIdx] = savedFields[id][fphIdx];
            }
          }
        } catch (e) {
          console.error("Failed to load custom fields", e);
        }
      }
    }

    function clearRepairInfo() {
      if (confirm("确定要清除所有维修信息（故障点、故障现象）吗？")) {
        var boardId = pcbdata.metadata.title + "_" + pcbdata.metadata.date;
        var key = "ibom_custom_fields_" + boardId;
        if (storage) {
          storage.removeItem(storagePrefix + key);
          location.reload();
        }
      }
    }

    function exportRepairInfo() {
      var boardId = pcbdata.metadata.title + "_" + pcbdata.metadata.date;
      var key = "ibom_custom_fields_" + boardId;
      var data = null;
      if (storage) {
        data = storage.getItem(storagePrefix + key);
      }
      if (!data) {
        alert("没有维修信息可导出 (No repair info to export)");
        return;
      }
      // Create export object with metadata
      var exportObj = {
        version: 1,
        board: {
          title: pcbdata.metadata.title,
          revision: pcbdata.metadata.revision,
          date: pcbdata.metadata.date
        },
        fields: config.fields,
        data: JSON.parse(data)
      };
      var jsonStr = JSON.stringify(exportObj, null, 2);
      var blob = new Blob([jsonStr], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      var filename = "RepairInfo_" + pcbdata.metadata.title + "_" + pcbdata.metadata.date + ".json";
      a.href = url;
      a.download = filename.replace(/[^a-zA-Z0-9_.-]/g, "_");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      alert("维修信息已导出: " + filename);
    }

    function importRepairInfo() {
      var input = document.createElement("input");
      input.type = "file";
      input.accept = ".json,application/json";
      input.onchange = function(e) {
        var file = e.target.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function(evt) {
          try {
            var importObj = JSON.parse(evt.target.result);
            // Validate version
            if (!importObj.version || importObj.version !== 1) {
              alert("不支持的文件格式版本 (Unsupported file version)");
              return;
            }
            // Validate board match (warn but allow override)
            var currentBoard = pcbdata.metadata.title + "_" + pcbdata.metadata.revision;
            var importBoard = (importObj.board.title || "") + "_" + (importObj.board.revision || "");
            if (currentBoard !== importBoard) {
              var proceed = confirm("警告: 文件来自不同的板子\\n" +
                "当前: " + currentBoard + "\\n" +
                "文件: " + importBoard + "\\n\\n" +
                "仍要继续导入吗？");
              if (!proceed) return;
            }
            // Save to localStorage
            var boardId = pcbdata.metadata.title + "_" + pcbdata.metadata.date;
            var key = "ibom_custom_fields_" + boardId;
            if (storage) {
              storage.setItem(storagePrefix + key, JSON.stringify(importObj.data));
              alert("导入成功，页面将刷新以显示数据");
              location.reload();
            }
          } catch (err) {
            alert("导入失败: " + err.message);
          }
        };
        reader.readAsText(file);
      };
      input.click();
    }
"""
    anchor = 'function populateBomHeader'
    if anchor in content:
        content = content.replace(anchor, js_persistence + '\n    ' + anchor, 1)
        print("  [OK] JS persistence functions injected before populateBomHeader")
    else:
        # Fallback: inject right after opening <script> tag
        script_tag = '<script type="text/javascript">'
        if script_tag in content:
            content = content.replace(script_tag, script_tag + '\n' + js_persistence, 1)
            print("  [OK] (fallback) JS persistence functions injected after <script> tag")
        else:
            print("  [WARN] Could not find injection point for JS functions!")

    # =========================================================================
    # Step 4: Call loadCustomFields() after initDone = true
    #
    # RATIONALE: The iBOM window.onload sequence is:
    #   initRender()   - canvas mouse handlers only
    #   initStorage()  - initialises 'storage' and 'storagePrefix'  <-- needed!
    #   initDefaults()
    #   ...
    #   initDone = true;   <-- safe injection point (all deps ready)
    #   changeBomLayout()  <-- first render triggered here
    #
    # Previous code injected after initRender() which ran BEFORE initStorage(),
    # causing loadCustomFields() to silently fail (storage was null).
    # =========================================================================
    print("\n[Step 4] Injecting loadCustomFields() call...")
    # 'initDone = true;' appears TWICE in iBOM:
    #   1st: inside overwriteSettings() - WRONG target
    #   2nd: inside window.onload       - CORRECT target (after initStorage)
    # Use rfind to get the last occurrence (window.onload).
    INJECT_AFTER = 'initDone = true;'
    idx = content.rfind(INJECT_AFTER)
    if idx != -1:
        insert_pos = idx + len(INJECT_AFTER)
        content = content[:insert_pos] + '\n  loadCustomFields();' + content[insert_pos:]
        print("  [OK] loadCustomFields() injected after last 'initDone = true;' (window.onload)")
    else:
        # Fallback: inject via a separate <script> before </body>
        fallback_script = (
            '\n<script>\n'
            'window.addEventListener("load", function() {\n'
            '  if (typeof loadCustomFields === "function" && typeof storage !== "undefined") {\n'
            '    loadCustomFields();\n'
            '  }\n'
            '});\n'
            '</script>\n'
        )
        if '</body>' in content:
            content = content.replace('</body>', fallback_script + '</body>', 1)
            print("  [WARN] 'initDone = true;' not found - used fallback window.load event")
        else:
            print("  [WARN] Could not inject loadCustomFields() call!")


    # =========================================================================
    # Step 5: Inject Repair Info UI button into IO menu
    # Anchors before the "Save bom table as" menu label.
    # =========================================================================
    print("\n[Step 5] Injecting Repair Info menu button...")
    menu_label_pattern = r'(<div class="menu-label">\s*<span[^>]*>Save bom table as</span>)'
    menu_clear_btn = """
            <div class="menu-label menu-label-top">
              <span style="margin-left: 5px; font-weight: bold;">维修信息 (Repair Info)</span>
              <div class="flexbox" style="margin-top: 5px; gap: 5px;">
                <button class="savebtn" style="flex: 1; cursor: pointer; padding: 5px; font-size: 12px;"
                        onclick="exportRepairInfo()">导出 (Export)</button>
                <button class="savebtn" style="flex: 1; cursor: pointer; padding: 5px; font-size: 12px;"
                        onclick="importRepairInfo()">导入 (Import)</button>
              </div>
              <div class="flexbox" style="margin-top: 5px;">
                <button class="savebtn" style="width: 100%; cursor: pointer; padding: 5px; font-size: 12px;"
                        onclick="clearRepairInfo()">清除所有 (Clear All)</button>
              </div>
            </div>
            """
    before = content
    content = re.sub(menu_label_pattern, menu_clear_btn + r'\1', content)
    if content != before:
        print("  [OK] Repair Info menu button injected")
    else:
        print("  [WARN] Menu label pattern not found - button NOT injected")

    # =========================================================================
    # Step 6: Inject editable-cell double-click logic into populateBomBody
    # This pattern targets the code path that handles custom fields (the else
    # branch that processes arbitrary config.fields entries).
    # After matching, we insert the ondblclick handler for 故障点/故障现象.
    # =========================================================================
    print("\n[Step 6] Injecting editable cell logic into populateBomBody...")
    field_proc_pattern = (
        r'(var\s+field_index\s*=\s*config\.fields\.indexOf\(column\);?'
        r'\s*if\s*\(field_index\s*<\s*0\)\s*return;'
        r'\s*var\s+valueSet\s*=\s*new\s+Set\(\);'
        r'\s*[^;]+;'
        r'\s*td\s*=\s*document\.createElement\("TD"\);)'
    )

    editable_logic = """
                            if (settings.bommode === "ungrouped" &&
                                (column === "故障点" || column === "故障现象")) {
                                td.classList.add("editable-cell");
                                td.title = "Double click to edit / 双击编辑";
                                td.ondblclick = (function(td_el, id_val, f_idx) {
                                    return function(e) {
                                        e.stopPropagation();
                                        if (td_el.querySelector('input')) return;
                                        var originalValue = pcbdata.bom.fields[id_val][f_idx] || "";
                                        var input = document.createElement('input');
                                        input.type = 'text';
                                        input.value = originalValue;
                                        input.className = "cell-edit-input";
                                        td_el.innerHTML = '';
                                        td_el.appendChild(input);
                                        input.focus();
                                        function commit() {
                                            var newValue = input.value.trim();
                                            pcbdata.bom.fields[id_val][f_idx] = newValue;
                                            td_el.innerHTML = highlightFilter(String(newValue));
                                            saveCustomFields();
                                        }
                                        input.onblur = commit;
                                        input.onkeydown = function(evt) {
                                            if (evt.key === 'Enter') { input.blur(); }
                                            if (evt.key === 'Escape') {
                                                td_el.innerHTML = highlightFilter(String(originalValue));
                                            }
                                        };
                                    };
                                })(td, references[0][1], field_index);
                            }
    """

    def replacement(m):
        return m.group(0) + editable_logic

    before = content
    content = re.sub(field_proc_pattern, replacement, content)
    if content != before:
        print("  [OK] Editable cell logic injected into populateBomBody")
    else:
        print("  [WARN] Editable cell pattern NOT matched - double-click editing will NOT work")
        print("         Check that the iBOM JS structure contains the expected field-processing code")

    # =========================================================================
    # Write output
    # =========================================================================
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\nDone. Output: {output_file}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python patch_ibom.py <input.html> [output.html]")
    else:
        inf = sys.argv[1]
        if len(sys.argv) > 2:
            outf = sys.argv[2]
        else:
            base = os.path.basename(inf)
            outf = "Repair-Guide_" + base
        patch_html(inf, outf)
