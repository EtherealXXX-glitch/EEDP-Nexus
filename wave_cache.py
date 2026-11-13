"""Bounded multiresolution viewport cache. Panning never waits for RPC."""


class WaveCache:
    def __init__(self, limit=8):
        self.limit=limit
        self.views=[]
        self.overview=None

    def add(self, data):
        if data["start_sample"]==0 and data["sample_count"]==data["total_samples"]:
            self.overview=data
        key=(data["start_sample"],data["sample_count"],data["bin_samples"])
        self.views=[view for view in self.views if (view["start_sample"],view["sample_count"],view["bin_samples"])!=key]
        self.views.append(data)
        self.views=self.views[-self.limit:]

    def window(self, start, count, pixels):
        candidates=list(self.views)
        if self.overview is not None: candidates.append(self.overview)
        if not candidates:return None,False
        total=candidates[-1]["total_samples"]
        count=max(1,min(count or total,total))
        start=max(0,min(start,total-count))
        covering=[view for view in candidates if view["start_sample"]<=start and
                  view["start_sample"]+view["sample_count"]>=start+count]
        if not covering:return None,False
        source=min(covering,key=lambda view:view["bin_samples"])
        step=source["bin_samples"]
        first=max(0,(start-source["start_sample"])//step)
        last=(start+count-source["start_sample"]+step-1)//step
        return {**source,"start_sample":start,"sample_count":count,
            "bucket_start_sample":source["start_sample"]+first*step,
            "channels":[{"name":channel["name"],"ranges":channel["ranges"][first:last]} for channel in source["channels"]]}, step<=max(1,count/max(1,pixels))
