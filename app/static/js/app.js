/* ¿Qué cocino hoy? — JavaScript mínimo.
   Todo funciona sin JS; esto solo mejora la experiencia. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function postForm(form) {
    return fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    }).then(function (res) {
      if (!res.ok) { throw new Error("HTTP " + res.status); }
      return res.json();
    });
  }

  function updateShoppingBadges(pending) {
    $all(".bottom-nav .dot, .navbar .badge").forEach(function (el) {
      if (pending > 0) { el.textContent = pending; } else { el.remove(); }
    });
    var counter = $("[data-pending-count]");
    if (counter) { counter.textContent = pending; }
  }

  // Cerrar alertas
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-dismiss]");
    if (btn) { btn.closest(".alert").remove(); }
  });

  // Confirmaciones
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      e.preventDefault();
    }
  }, true);

  // Lista de compras: marcar y eliminar sin recargar
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches("[data-toggle-item], [data-delete-item]")) { return; }
    e.preventDefault();
    var li = form.closest(".shop-item");
    postForm(form).then(function (data) {
      if (data.deleted) {
        var list = li.parentElement;
        li.remove();
        if (!list.children.length) { list.closest(".shop-group").remove(); }
      } else {
        li.classList.toggle("shop-item--done", data.checked);
        var check = $(".check", li);
        check.setAttribute("aria-checked", data.checked ? "true" : "false");
        check.firstElementChild.textContent = data.checked ? "✓" : "";
      }
      updateShoppingBadges(data.pending);
    }).catch(function () { form.submit(); });
  });

  // Favoritos sin recargar
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches("[data-favorite]")) { return; }
    e.preventDefault();
    postForm(form).then(function (data) {
      var btn = $("button", form);
      btn.classList.toggle("fav--on", data.favorite);
      btn.setAttribute("aria-pressed", data.favorite ? "true" : "false");
      btn.firstElementChild.textContent = data.favorite ? "❤️" : "🤍";
      $("[data-label]", btn).textContent = data.favorite ? "Guardada" : "Guardar";
    }).catch(function () { form.submit(); });
  });

  // Modales (<dialog>)
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-open-modal]");
    if (opener) {
      var dialog = document.getElementById(opener.dataset.openModal);
      if (dialog && dialog.showModal) { e.preventDefault(); dialog.showModal(); }
    }
    var closer = e.target.closest("[data-close-modal]");
    if (closer) { closer.closest("dialog").close(); }
  });

  // Autoenvío (p. ej. cambiar número de personas)
  $all("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });
  $all("[data-autosubmit-hide]").forEach(function (el) { el.classList.add("hidden"); });

  // "Agregar otro ingrediente": crea un chip marcado
  $all("[data-extra]").forEach(function (wrap) {
    var input = $("input", wrap);
    var button = $("button", wrap);
    var target = document.getElementById(wrap.dataset.extra);
    function add() {
      var value = input.value.trim();
      if (!value) { return; }
      value.split(",").forEach(function (raw) {
        var name = raw.trim().slice(0, 40);
        if (!name) { return; }
        var label = document.createElement("label");
        label.className = "chip";
        var cb = document.createElement("input");
        cb.type = "checkbox"; cb.name = "extra"; cb.value = name; cb.checked = true;
        var span = document.createElement("span");
        span.textContent = "➕ " + name;
        label.appendChild(cb); label.appendChild(span);
        target.appendChild(label);
      });
      input.value = "";
      input.name = "";  // evita enviar el texto dos veces
      input.focus();
    }
    button.addEventListener("click", add);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); add(); }
    });
    input.addEventListener("input", function () { input.name = "extra"; });
  });

  // Onboarding por pasos
  var ob = $("[data-onboarding]");
  if (ob) {
    var steps = $all(".ob-step", ob);
    var bars = $all(".progress span", ob);
    var prev = $("[data-prev]", ob), next = $("[data-next]", ob), finish = $("[data-finish]", ob);
    var current = 0;
    function show(i) {
      current = i;
      steps.forEach(function (s, n) { s.classList.toggle("current", n === i); });
      bars.forEach(function (b, n) { b.classList.toggle("on", n <= i); });
      prev.classList.toggle("hidden", i === 0);
      next.classList.toggle("hidden", i === steps.length - 1);
      finish.classList.toggle("hidden", i !== steps.length - 1);
      window.scrollTo(0, 0);
    }
    prev.addEventListener("click", function () { show(Math.max(0, current - 1)); });
    next.addEventListener("click", function () { show(Math.min(steps.length - 1, current + 1)); });
    show(0);

    // "No tengo restricciones" desmarca el resto
    var none = $("input[name=no_restrictions]", ob);
    if (none) {
      none.addEventListener("change", function () {
        if (none.checked) {
          $all("input[name=excluded_ingredients], input[name=restrictions]", ob).forEach(function (c) { c.checked = false; });
        }
      });
      $all("input[name=excluded_ingredients], input[name=restrictions]", ob).forEach(function (c) {
        c.addEventListener("change", function () { if (c.checked) { none.checked = false; } });
      });
    }
  }

  // Filtro rápido de chips en selectores largos
  $all("[data-chip-filter]").forEach(function (input) {
    var root = document.getElementById(input.dataset.chipFilter);
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
      $all(".chip", root).forEach(function (chip) {
        var text = chip.textContent.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
        chip.classList.toggle("hidden", q && text.indexOf(q) === -1);
      });
      if (q) { $all("details.more", root).forEach(function (d) { d.open = true; }); }
    });
  });
})();
