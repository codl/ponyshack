// I suck at everything javascript
// :S

function hasClass(ele, cls) {
    return ele.className.match(new RegExp('(\\s|^)' + cls + '(\\s|$)'));
}
function addClass(ele, cls) {
    if (!this.hasClass(ele, cls)) ele.className += " " + cls;
}
function removeClass(ele, cls) {
    if (hasClass(ele, cls)) {
        var reg = new RegExp('(\\s|^)' + cls + '(\\s|$)');
        ele.className = ele.className.replace(reg, ' ');
    }
}

var boxactivity = function(e){
    if (this.timeout) {
        window.clearTimeout(this.timeout);
    }
    if (this.aclist && e.keyCode && e.keyCode == 38 || e.keyCode == 40 || e.keyCode == 13){
        // 40 : down, 38 : up, 13 = enter
        e.preventDefault()
        var active = this.aclist.getElementsByClassName("active")
        if (active.length > 0){
            var sibling = null
            if (e.keyCode == 13) {
                add_tag(active[0].getAttribute("tag_name"), this);
            } else if(e.keyCode == 40){
                sibling = active[0].nextSibling;
            } else if(e.keyCode == 38){
                sibling = active[0].previousSibling;
            }
            active[0].className = ""
            if(sibling){
                sibling.className = "active";
            }
        } else if ( e.keyCode == 40 ) {
            firstresult = this.aclist.firstChild;
            if (firstresult){
                firstresult.className = "active";
            }
        } else if ( e.keyCode == 38 ) {
            lastresult = this.aclist.lastChild;
            if (lastresult){
                lastresult.className = "active";
            }
        } else if ( e.keyCode == 13 ) {
            if (this.parentNode.id == "searchbar"){
                document.location = "/" + this.value;
            } else {
                this.parentNode.submit();
            }
        }
    } else {
        this.timeout = window.setTimeout(autocomplete, 100, this);
    }
}

var boxblur = function(){
    if (this.timeout) {
        window.clearTimeout(this.timeout);
    }
    this.timeout = window.setTimeout(function(box){
        box.aclist.style.display = "none"
        }, 700, this);
}

var updateaclist = function(e, box){
    if (!box.aclist){
        box.aclist = document.createElement("ul");
        box.aclist.box = box
        box.aclist.setAttribute("class", "autocomplete_list")
        box.aclist.style.display = "none";
        box.aclist.style.position = "absolute";
        box.aclist.style.top = box.offsetTop + box.offsetHeight - 1 + "px";
        box.aclist.style.left = box.offsetLeft + "px";
        box.aclist.style.minWidth = (box.offsetWidth - 2) + "px";
        box.aclist.addEventListener('click', function(){window.clearTimeout(box.timeout)}, false);
        document.body.appendChild(box.aclist);
    }
    box.aclist.innerHTML = e.currentTarget.responseText
    box.aclist.style.display = "block"
    for (var i = 0; i < box.aclist.childNodes.length; i++){
        tag = box.aclist.childNodes[i];
        tag.addEventListener('click', click_tag, false);
    }
}



var autocomplete = function(box){
    box.xhr = new XMLHttpRequest();
    box.xhr.open("GET", "/api/autocomplete?q="+box.value);
    box.xhr.send(null)
    box.xhr.addEventListener('load', function(e){updateaclist(e, box);}, false);
    }

var click_tag = function(e){
    tag = e.currentTarget;
    tagname = tag.getAttribute("tag_name");
    box = tag.parentNode.box;
    add_tag(tagname, box)
}

var add_tag = function(tag, box){
    taglist = box.value.split(",");
    box.value=""
    for (var i = 0; i < taglist.length-1; i++){
        box.value += taglist[i].trim() + ", ";
    }
    box.value += tag + ", ";
    autocomplete(box);
    box.scrollLeft = box.scrollWidth - box.clientWidth
    box.focus();
}

autocomplete_boxes = document.getElementsByClassName("autocomplete");

for (var i=0; i < autocomplete_boxes.length; i++) {
    box = autocomplete_boxes[i];
    box.addEventListener("focus", boxactivity, false);
    box.addEventListener("keydown", boxactivity, false);
    box.addEventListener("blur", boxblur, false);
}

var edit_boxes = document.getElementsByClassName("edit-box");
if (edit_boxes.length != 0) {
    for (var i=0; i < edit_boxes.length; i++){
        box = edit_boxes[i];
        addClass(box, "hidden");
    }
}

function showeditboxes(e){
    e.preventDefault()
    var edit_boxes = document.getElementsByClassName("edit-box");
    if (edit_boxes.length != 0) {
        for (var i=0; i < edit_boxes.length; i++){
            box = edit_boxes[i];
            removeClass(box, "hidden");
        }
    }
    addClass(e.currentTarget, "hidden");
}

var editlink = document.getElementById("edit-link");
if (editlink){
    removeClass(editlink, "hidden");
    editlink.addEventListener("click", showeditboxes, false);
}
