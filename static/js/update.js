// Copyright 2009-2011 I'm Everyone
// Copyright 2009 FriendFeed

$(function() {
    if (!window.console) window.console = {};
    if (!window.console.log) window.console.log = function() {};

    $("#messageform").live("submit", function() {
    	newMessage($(this));
    	return false;
    });
    
    $("#messageform").live("keypress", function(e) {
    	if (e.keyCode == 13) {
    	    newMessage($(this));
    	    return false;
    	}
    });
    
    // Start updater polling for new updates on page load
    $("#message").select();
    // 2 second delay for Google chrome so page stops loading - see 
    // http://stackoverflow.com/questions/2703861
    window.setTimeout("updater.poll()",1000);
    // updater.poll();
});

function newMessage(form) {
    // Post top-level messages
    var message = form.formToDict();
    var disabled = form.find("input[type=submit]");
    disabled.disable();
    $.postJSON("/message/new", message, function(response) {
	updater.showMessage(response);
	if (message.id) {
	    form.parent().remove();
	} else {
	    form.find("input[type=text]").val("").select();
	    disabled.enable();
	}
    });
}

function getCookie(name) {
    var r = document.cookie.match("\\b" + name + "=([^;]*)\\b");
    return r ? r[1] : undefined;
}

jQuery.postJSON = function(url, args, callback) {
    args._xsrf = getCookie("_xsrf");
    $.ajax({url: url, data: $.param(args), dataType: "text", type: "POST",
	    success: function(response) {
	if (callback) callback(eval("(" + response + ")"));
    }, error: function(response) {
	console.log("ERROR:", response)
    }});
};

jQuery.fn.formToDict = function() {
    var fields = this.serializeArray();
    var json = {}
    for (var i = 0; i < fields.length; i++) {
	json[fields[i].name] = fields[i].value;
    }
    if (json.next) delete json.next;
    return json;
};

jQuery.fn.disable = function() {
    this.enable(false);
    return this;
};

jQuery.fn.enable = function(opt_enable) {
    if (arguments.length && !opt_enable) {
        this.attr("disabled", "disabled");
    } else {
        this.removeAttr("disabled");
    }
    return this;
};

// Requests server to send update when available
var updater = {
    errorSleepTime: 500,
    cursor: null,
    poll: function() {
    	var args = {"_xsrf": getCookie("_xsrf")};
    	if (updater.cursor) args.cursor = updater.cursor;
        	$.ajax({url: window.location.pathname+"/update", 
        	    type: "POST", 
        	    dataType: "text",
        		data: $.param(args), 
        		success: updater.onSuccess,
        		error: updater.onError});
    },

    onSuccess: function(response) {
    	try {
    	    updater.newMessages(eval("(" + response + ")"));
    	} catch (e) {
    	    updater.onError();
    	    return;
    	}
    	updater.errorSleepTime = 500;
    	window.setTimeout(updater.poll, 0);
    },

    onError: function(response) {
    	updater.errorSleepTime *= 2;
    	console.log("Poll error; sleeping for", updater.errorSleepTime, "ms");
    	window.setTimeout(updater.poll, updater.errorSleepTime);
    },

    newMessages: function(response) {
    	if (!response.messages) return;
        	updater.cursor = response.cursor;
        	var messages = response.messages;
        	updater.cursor = messages[messages.length - 1].id;
        	
        	console.log(messages.length, "new messages, cursor:", updater.cursor);
        	for (var i = 0; i < messages.length; i++) {
        	    updater.showMessage(messages[i]);
        	}
    },

    // Append message to page
    showMessage: function(message) {
        
        // Create newmessage
    	var newmessage = $(message.html);
        newmessage.hide();
    	
    	// Slide down and add newelement underneath parent
    	function addcomment(parent, newmessage) {
    	    parent.append(newmessage);
    	    newmessage.slideDown();
    	    newmessage.effect("highlight", {}, 3000);
        }
    	
    	// Add new comments and messages apropriately
    	if ( message.parentid == null ) {
    	    // Top level post
    	    $("#messages").prepend(newmessage);
        	newmessage.slideDown();
    	} else if ( message.parentid == message.thread ) {
    	    // Top level comment, added to top level of tree WORKS    
    	    var parent = $("#commenttree");
    	    addcomment(parent, newmessage);
    	} else {
    	    // Downlevel comment, added beneath parent NO WORK
    	    var parent = $("#" + message.parentid);
    	    parent.effect("highlight", {}, 3000);
    	    // Now: find out of there's an existing ul or we need to make one
    	    if (parent.find("ul").length == 0) {
    	        // Add our element directly inside parents own ul 
    	        newmessage = $("<ul>"+message.html+"</ul>");
    	    } else {
                // Add our element underneath the existing ul
                parent = parent.children("ul").first();
    	    }
    	    addcomment(parent, newmessage);
    	    
    	}
    }
};
