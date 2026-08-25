(function (global) {
  function lookup(data, path) {
    var cur = data;
    String(path || "").split(".").forEach(function (key) {
      if (cur == null || key === "") return;
      cur = cur[key];
    });
    return cur;
  }

  function cloneTemplate(id) {
    var template = document.getElementById(id);
    if (!template) {
      throw new Error('Template with ID "' + id + '" not found.');
    }
    return document.importNode(template.content, true);
  }

  function bind(root, data) {
    root.querySelectorAll("[data-bind]").forEach(function (el) {
      var value = lookup(data, el.getAttribute("data-bind"));
      el.textContent = value == null ? "" : String(value);
    });
    root.querySelectorAll("[data-if]").forEach(function (el) {
      if (!lookup(data, el.getAttribute("data-if"))) el.remove();
    });
    root.querySelectorAll("[data-unless]").forEach(function (el) {
      if (lookup(data, el.getAttribute("data-unless"))) el.remove();
    });
    Array.prototype.forEach.call(root.querySelectorAll("*"), function (el) {
      Array.prototype.forEach.call(el.attributes, function (attr) {
        if (attr.name.indexOf("data-attr-") !== 0) return;
        var name = attr.name.slice("data-attr-".length);
        var value = lookup(data, attr.value);
        if (value == null || value === false) el.removeAttribute(name);
        else el.setAttribute(name, value === true ? name : String(value));
      });
    });
  }

  function renderList(templateId, dataArray, populateFn) {
    var fragment = document.createDocumentFragment();
    (dataArray || []).forEach(function (item, index) {
      var clone = cloneTemplate(templateId);
      if (populateFn) populateFn(clone, item, index);
      fragment.appendChild(clone);
    });
    return fragment;
  }

  function mount(container, node) {
    container.replaceChildren(node);
  }

  function setFill(el, pct) {
    if (!el) return;
    var n = Math.max(0, Math.min(100, Number(pct) || 0));
    el.style.setProperty("--fill", n + "%");
  }

  global.BearingTpl = {
    lookup: lookup,
    cloneTemplate: cloneTemplate,
    bind: bind,
    renderList: renderList,
    mount: mount,
    setFill: setFill
  };
})(window);
