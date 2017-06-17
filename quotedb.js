var QUOTEDB_DOCUMENTS = [{
	"id": 1,
	"users": ["vebyast"],
	"lines": ["[4:52 PM] veByast: Yes, that's something I definitely haven't been doing.(edited)",
			  "[4:52 PM] veByast: I'm working off my own experience writing research papers in a hurry, which I think should transfer.",
			  "[4:53 PM] veByast: But I can't quite replicate the part where they're getting their underlying information by speed-reading transcripts and reports requested of anyone on the Courageous that's talked to someone from the ISC."],
	"uploaded": Date.parse("2017-06-17T03:36Z")
},{
	"id": 3,
	"users": ["vebyast"],
	"lines": ["[4:52 PM] veByast: AHSDFLKHJASDFHYALSIFYH."],
	"uploaded": Date.parse("2017-06-17T03:42Z")
},{
	"id": 2,
	"users": ["asdf"],
	"lines": ["[4:52 PM] asdf: TESTING"],
	"uploaded": Date.parse("20170617T0336Z")
}];

var QUOTEDB_MAP = {};
QUOTEDB_DOCUMENTS.forEach(function (doc) {
	QUOTEDB_MAP[doc['id']] = doc;
	doc['text'] = doc['lines'].join("<br />")
});

var idx = lunr(function () {
	this.ref('id');
	this.field('text');
	this.field('users');

	QUOTEDB_DOCUMENTS.forEach(function (doc) {
		this.add(doc);
	}, this);
});

var search_results_vue;
$(document).ready(function() {
	search_results_vue = new Vue({
		el: '#search_results',
		data: {
			search_results: [],
		}
	});

	$('#search_query_box').keypress(function(e) {
        if (e.keyCode == 13) {
			$('#search_query_submit_button').click();
			return false;
		};
	});
});

function search_quote_db() {
	query = $('#search_query_box').val();
	results = idx.search(query);
	result_documents = results.map(function(sr) {
		doc = QUOTEDB_MAP[sr.ref]
		return {
			"uploaded": (new Date(doc["uploaded"])).toLocaleDateString(),
			"lines": doc["lines"],
		}
	});
	search_results_vue.search_results = result_documents;
};
