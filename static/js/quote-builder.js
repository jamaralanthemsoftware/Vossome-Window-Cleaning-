(function () {
  "use strict";
  var form = document.querySelector("[data-quote-builder]");
  if (!form) return;

  function field(name) { return form.querySelector('[name="' + name + '"]'); }
  function money(n) {
    var r = Math.round((n + Number.EPSILON) * 100) / 100;
    return "$" + (Number.isInteger(r) ? r.toLocaleString("en-US") : r.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  }
  function qty(n) { return Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 }); }
  function num(name) {
    var el = field(name);
    if (!el || el.disabled) return null;
    var v = String(el.value).trim().replace(/,/g, "");
    if (v === "") return null;
    var n = parseFloat(v);
    return isFinite(n) && n >= 0 ? n : null;
  }
  function on(name) {
    var el = field(name);
    if (!el || el.disabled) return false;
    if (el.type === "checkbox") return el.checked;
    return String(el.value).toLowerCase() === "yes";
  }
  function val(name) {
    var el = field(name);
    if (el && el.type === "radio") el = form.querySelector('[name="' + name + '"]:checked');
    return el && !el.disabled ? String(el.value).toLowerCase() : "";
  }

  var MATCHERS = [["window", /window/], ["gutter", /gutter/], ["house", /house/], ["deck", /deck/], ["surface", /driveway|patio|walkway|surface|concrete|pressure/]];
  var LABELS = { window: "Window cleaning", gutter: "Gutter cleaning", house: "House washing", surface: "Driveway, patio & walkway", deck: "Deck cleaning", other: "Other service" };

  function serviceKey(input) {
    var slugs = { "window-cleaning": "window", "gutter-cleaning": "gutter", "pressure-washing": "house", "concrete-patio-cleaning": "surface", "deck-cleaning": "deck", "other": "other" };
    if (slugs[input.value]) return slugs[input.value];
    var lab = input.closest("label");
    if (!lab && input.id) lab = form.querySelector('label[for="' + input.id + '"]');
    var text = ((lab ? lab.textContent : "") + " " + input.value).toLowerCase();
    for (var i = 0; i < MATCHERS.length; i++) if (MATCHERS[i][1].test(text)) return MATCHERS[i][0];
    return "other";
  }

  var serviceInputs = Array.prototype.slice.call(form.querySelectorAll('input[name="services"]'));
  var panels = Array.prototype.slice.call(form.querySelectorAll("[data-service-panel]"));
  var summary = form.querySelector("[data-qb-summary]");
  var UNKNOWN = {
    window_unknown: ["window_count"],
    gutter_unknown: ["gutter_one", "gutter_one_half", "gutter_two", "gutter_three"],
    surface_unknown: ["surface_area", "surface_length", "surface_width"],
    deck_unknown: ["deck_area", "deck_railing"]
  };

  Array.prototype.forEach.call(form.querySelectorAll('input[type="number"]'), function (el) {
    el.setAttribute("inputmode", "decimal");
    el.setAttribute("min", "0");
    el.setAttribute("autocomplete", "off");
  });

  function selectedKeys() {
    var keys = [];
    serviceInputs.forEach(function (i) {
      if (i.checked) { var k = serviceKey(i); if (keys.indexOf(k) < 0) keys.push(k); }
    });
    return keys;
  }

  function syncPanels(keys) {
    panels.forEach(function (p) {
      var active = keys.indexOf(p.getAttribute("data-service-panel")) >= 0;
      p.hidden = !active;
      Array.prototype.forEach.call(p.querySelectorAll("input, select, textarea"), function (el) { el.disabled = !active; });
    });
    Object.keys(UNKNOWN).forEach(function (name) {
      var box = field(name);
      if (!box || box.disabled) return;
      UNKNOWN[name].forEach(function (n) { var el = field(n); if (el) el.disabled = box.checked; });
    });
    var under = form.querySelector("[data-underside-copy]");
    if (under) under.hidden = !on("deck_underside");
  }

  function compute(keys) {
    var out = [];
    keys.forEach(function (k) {
      var line = { service: k, label: LABELS[k], amount: null, status: "review", reasons: [], calculation: "" };
      if (k === "window") {
        var n = num("window_count");
        if (n !== null && n > 0) {
          line.amount = 100 + n * 10; line.status = "estimate";
          line.calculation = "$100 to come out + " + qty(n) + " windows × $10 = " + money(line.amount) + " estimated total";
        } else {
          line.calculation = "No window count yet, so no price is calculated.";
          line.reasons.push("We’ll count the windows at your appointment.");
        }
      } else if (k === "gutter") {
        var rates = [["gutter_one", 1, "1-story"], ["gutter_one_half", 1.5, "1½-story"], ["gutter_two", 2, "2-story"], ["gutter_three", 3, "3-story"]];
        var sum = 0, parts = [], any = false;
        rates.forEach(function (r) {
          var f = num(r[0]);
          if (f !== null && f > 0) { any = true; sum += f * r[1]; parts.push(qty(f) + " ft " + r[2] + " × " + money(r[1])); }
        });
        if (any) {
          line.amount = Math.max(180, sum); line.status = "estimate";
          line.calculation = parts.join(" + ") + " = " + money(sum) + (sum < 180 ? "; the $180 minimum applies, so " + money(180) : "") + " estimated total";
        } else {
          line.calculation = "Gutter cleaning has a $180 minimum. It isn’t counted as a total until you give us some footage.";
          line.reasons.push("We’ll measure at your appointment.");
        }
      } else if (k === "house") {
        var qs = ["house_three_stories", "house_large", "house_roof"], allNo = true;
        qs.forEach(function (q) { if (val(q) !== "no") allNo = false; });
        if (allNo) {
          line.amount = 400; line.status = "estimate"; line.calculation = "Standard house wash, flat rate = $400 estimated total";
        } else {
          line.calculation = "A flat $400 applies to a standard house. We need a few more details first.";
          if (val("house_three_stories") === "yes") line.reasons.push("Three stories tall");
          if (val("house_large") === "yes") line.reasons.push("Larger than 4,000 square feet");
          if (val("house_roof") === "yes") line.reasons.push("Roof access needed");
          if (!line.reasons.length) line.reasons.push("Answer the three questions above, or we’ll go over them with you.");
        }
      } else if (k === "surface") {
        var area = num("surface_area"), l = num("surface_length"), w = num("surface_width"), sq = null, how = "";
        if (area !== null && area > 0) { sq = area; how = qty(sq) + " sq ft"; }
        else if (l !== null && w !== null && l > 0 && w > 0) { sq = l * w; how = qty(l) + " ft × " + qty(w) + " ft = " + qty(sq) + " sq ft"; }
        if (sq !== null) {
          line.amount = sq * 0.4; line.status = "estimate";
          line.calculation = how + " × $0.40 = " + money(line.amount) + " estimated total";
        } else {
          line.calculation = "No size yet, so no price is calculated.";
          line.reasons.push("We’ll measure at your appointment.");
        }
      } else if (k === "deck") {
        var a = num("deck_area"), r = num("deck_railing"), t = 0, bits = [];
        if (a !== null && a > 0) { t += a * 0.5; bits.push(qty(a) + " sq ft × $0.50"); }
        if (r !== null) { t += r * 2; bits.push(qty(r) + " ft railing × $2"); }
        if (a !== null && a > 0 && r !== null) { line.amount = t; line.calculation = bits.join(" + ") + " = " + money(t) + " ballpark"; }
        else line.calculation = "No size yet, so no ballpark is calculated.";
        if (a === null || a === 0) line.reasons.push("Walking-surface square footage is missing.");
        if (r === null) line.reasons.push("Railing length is missing (enter 0 if there is none).");
        if (["wood", "composite"].indexOf(val("deck_material")) < 0) line.reasons.push("Deck material needs review.");
        if (on("deck_stairs")) line.reasons.push("Stairs are priced separately and are not included in this number.");
        if (on("deck_underside")) line.reasons.push("Underside cleaning is a separate project and is not included. Photos please.");
        line.status = line.reasons.length ? "review" : "estimate";
      } else {
        line.calculation = "Reviewed individually.";
        line.reasons.push("No automatic price for this service.");
      }
      if (line.amount !== null) line.amount = Math.round((line.amount + Number.EPSILON) * 100) / 100;
      out.push(line);
    });
    return out;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function render(keys, lines) {
    summary.textContent = "";
    if (!lines.length) {
      summary.appendChild(el("p", "qb-summary-empty", "Select a service above to see a running estimate. It’s only an estimate; we confirm counts, measurements, and the exact price at your appointment, and you give the okay before we start."));
      return;
    }
    var complete = lines.every(function (l) { return l.status === "estimate" && l.amount !== null; });
    var subtotal = 0, counted = 0;
    lines.forEach(function (l) { if (l.amount !== null) { subtotal += l.amount; counted++; } });

    var head = el("div", "qb-summary-head");
    if (complete) {
      head.appendChild(el("p", "qb-kicker", "Estimated total"));
      head.appendChild(el("p", "qb-total", money(subtotal)));
    } else {
      head.classList.add("is-partial");
      head.appendChild(el("p", "qb-kicker", counted ? "Partial estimate so far (not a total)" : "No total yet"));
      if (counted) head.appendChild(el("p", "qb-partial-amount", money(subtotal)));
      head.appendChild(el("p", "qb-review-note", "Some items need review, so this isn’t a complete price."));
    }
    summary.appendChild(head);

    var ul = el("ul", "qb-lines");
    lines.forEach(function (l) {
      var li = el("li", "qb-line qb-line--" + l.status);
      var top = el("div", "qb-line-top");
      top.appendChild(el("strong", "", l.label));
      top.appendChild(el("span", l.amount !== null ? "qb-amount" : "qb-amount qb-amount--none", l.amount !== null ? money(l.amount) : "No amount yet"));
      li.appendChild(top);
      if (l.status === "review") li.appendChild(el("span", "qb-flag", "Needs review"));
      if (l.calculation) li.appendChild(el("small", "", l.calculation));
      if (l.reasons.length) {
        var rs = el("ul", "qb-reasons");
        l.reasons.forEach(function (r) { rs.appendChild(el("li", "", r)); });
        li.appendChild(rs);
      }
      ul.appendChild(li);
    });
    summary.appendChild(ul);
    if (keys.indexOf("window") >= 0 && keys.length > 1) summary.appendChild(el("p", "qb-fine", "The $100 to come out applies once, to window cleaning only."));
    summary.appendChild(el("p", "qb-fine", "Estimates only. We confirm counts, measurements, expectations, and the exact price at your appointment, and you give the okay before we start. Underside and stairs are never in these numbers."));
  }

  function renderLive(lines) {
    Array.prototype.forEach.call(form.querySelectorAll("[data-live]"), function (p) {
      var l = null;
      lines.forEach(function (x) { if (x.service === p.getAttribute("data-live")) l = x; });
      p.textContent = l ? (l.amount !== null ? l.calculation : l.calculation) : "";
      p.classList.toggle("has-value", !!(l && l.amount !== null));
    });
  }

  function update() {
    var keys = selectedKeys();
    syncPanels(keys);
    var lines = compute(keys);
    render(keys, lines);
    renderLive(lines);
  }

  form.addEventListener("input", update);
  form.addEventListener("change", update);

  // Reply method toggles which contact field is required.
  var reply = Array.prototype.slice.call(form.querySelectorAll('input[name="preferred_reply_method"]'));
  function syncReply() {
    var chosen = reply.filter(function (r) { return r.checked; })[0];
    var m = chosen ? chosen.value : "";
    var phone = field("phone"), email = field("email");
    if (phone) phone.required = m === "text" || m === "call";
    if (email) email.required = m === "email";
    [["phone", phone], ["email", email]].forEach(function (p) {
      var wrap = form.querySelector('[data-contact-field="' + p[0] + '"]');
      if (wrap) wrap.classList.toggle("is-required", !!(p[1] && p[1].required));
    });
  }
  reply.forEach(function (r) { r.addEventListener("change", syncReply); });

  // Photo checks (client-side convenience only; the server validates again).
  var photos = field("photos"), photoError = form.querySelector("[data-photo-error]");
  if (photos && photoError) {
    photos.setAttribute("accept", "image/jpeg,image/png,image/webp");
    photos.addEventListener("change", function () {
      var files = Array.prototype.slice.call(photos.files || []), msg = "";
      if (files.length > 5) msg = "Please choose 5 photos or fewer.";
      files.forEach(function (f) {
        if (!msg && !/^image\/(jpeg|png|webp)$/.test(f.type)) msg = f.name + " isn’t a JPG, PNG, or WebP image.";
        if (!msg && f.size > 5 * 1024 * 1024) msg = f.name + " is over 5 MB.";
      });
      if (msg) photos.value = "";
      photoError.textContent = msg;
      photoError.hidden = !msg;
    });
  }

  syncReply();
  update();
})();
