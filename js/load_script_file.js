import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Load Script File: pick a script from the drop-down (the .txt/.md files in ComfyUI/input), or click
// "Choose file..." to open the system file dialog. The picked file is copied into ComfyUI/input and
// selected in the drop-down.
app.registerExtension({
    name: "ShotScript.LoadScriptFile",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "LoadScriptFile") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const node = this;
            const fileWidget = node.widgets?.find((w) => w.name === "file");
            if (!fileWidget) return result;

            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".txt,.md,text/plain,text/markdown";
            input.style.display = "none";
            document.body.append(input);

            input.onchange = async () => {
                const file = input.files?.[0];
                input.value = "";
                if (!file) return;
                try {
                    const body = new FormData();
                    body.append("file", file, file.name);
                    const resp = await api.fetchApi("/shot_script/upload", { method: "POST", body });
                    const json = await resp.json();
                    if (!resp.ok) throw new Error(json.error || `${resp.status} ${resp.statusText}`);
                    const values = fileWidget.options.values;
                    const placeholder = values.findIndex((v) => v.startsWith("[no "));
                    if (placeholder >= 0) values.splice(placeholder, 1);
                    if (!values.includes(json.name)) values.push(json.name);
                    fileWidget.value = json.name;
                    fileWidget.callback?.(json.name);
                    node.graph?.setDirtyCanvas(true, true);
                } catch (e) {
                    alert(`Could not load the script: ${e.message ?? e}`);
                }
            };

            // keep the button last: saved workflows store widget values by position
            const button = node.addWidget("button", "Choose file...", null, () => input.click());
            button.serialize = false;

            const onRemoved = node.onRemoved;
            node.onRemoved = function () {
                input.remove();
                return onRemoved?.apply(this, arguments);
            };
            return result;
        };
    },
});
