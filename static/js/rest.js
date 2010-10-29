$(document).ready(function() {
	// Add DELETE links
	$("a.delete").click(function(){
		var element = $(this);
		var noteid = element.attr("id");
		var info = 'id=' + noteid;

		$.ajax({
			type: "DELETE",
			url: this.href,
			data: info,
		});
		return false;
	});
	// Add PUT links
	$("a.put").click(function(){
		var element = $(this);
		var noteid = element.attr("id");
		var info = 'id=' + noteid;

		$.ajax({
			type: "PUT",
			url: this.href,
			data: info,
		});
		return false;
	});			
});